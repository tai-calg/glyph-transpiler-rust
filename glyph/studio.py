from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse
import webbrowser

from .compiler import GlyphError
from .incremental import IncrementalCompiler
from .studio_ui import STUDIO_HTML
from .studio_views import build_studio_views


@dataclass(frozen=True)
class StudioSnapshot:
    version: int
    status: str
    source: str
    digest: str
    updated_at: str
    diagnostics: tuple[dict[str, object], ...]
    artifacts: dict[str, str]
    semantic: dict[str, object]
    execution_ir: dict[str, object]
    glyph04_views: dict[str, object]

    def to_dict(self, source_path: Path, output_dir: Path) -> dict[str, object]:
        return {
            "version": self.version,
            "status": self.status,
            "source": self.source,
            "source_path": str(source_path),
            "output_dir": str(output_dir),
            "digest": self.digest,
            "updated_at": self.updated_at,
            "diagnostics": list(self.diagnostics),
            "artifact_names": sorted(self.artifacts),
            "semantic": self.semantic,
            "execution_ir": self.execution_ir,
            "glyph04_views": self.glyph04_views,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _source_digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


class GlyphStudio:
    """One-process development environment for one Glyph source file."""

    def __init__(self, input_path: str | Path):
        self.input_path = Path(input_path).resolve()
        self.output_dir = self.input_path.parent / ".glyph" / self.input_path.stem
        self.compiler = IncrementalCompiler()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._watcher: threading.Thread | None = None
        self._snapshot = StudioSnapshot(
            version=0,
            status="starting",
            source="",
            digest="",
            updated_at=_utc_now(),
            diagnostics=(),
            artifacts={},
            semantic={},
            execution_ir={},
            glyph04_views=build_studio_views({}),
        )

    @property
    def snapshot(self) -> StudioSnapshot:
        with self._lock:
            return self._snapshot

    def state_dict(self) -> dict[str, object]:
        with self._lock:
            return self._snapshot.to_dict(self.input_path, self.output_dir)

    def artifact(self, name: str) -> str | None:
        with self._lock:
            return self._snapshot.artifacts.get(name)

    def rebuild(self, source: str | None = None) -> StudioSnapshot:
        if source is None:
            source = self.input_path.read_text(encoding="utf-8")
        digest = _source_digest(source)
        previous = self.snapshot
        if previous.status == "ready" and previous.digest == digest:
            return previous

        try:
            result = self.compiler.compile_text(
                source,
                source_name=str(self.input_path),
                source_href=str(self.input_path),
            )
            compilation = result.snapshot
            semantic = json.loads(compilation.semantic_json)
            glyph04_views = build_studio_views(semantic)
            artifacts = {
                "generated.rs": compilation.artifacts.logic,
                "host.generated.rs": compilation.artifacts.host,
                "typed-ast.json": compilation.semantic_json,
                "studio-views.json": json.dumps(
                    glyph04_views,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                **compilation.diagrams.files,
            }
            for name, content in artifacts.items():
                _atomic_write(self.output_dir / name, content)
            execution_ir = json.loads(artifacts["execution-ir.json"])
            snapshot = StudioSnapshot(
                version=previous.version + 1,
                status="ready",
                source=source,
                digest=digest,
                updated_at=_utc_now(),
                diagnostics=(),
                artifacts=artifacts,
                semantic=semantic,
                execution_ir=execution_ir,
                glyph04_views=glyph04_views,
            )
        except (GlyphError, OSError, ValueError) as exc:
            snapshot = StudioSnapshot(
                version=previous.version + 1,
                status="error",
                source=source,
                digest=digest,
                updated_at=_utc_now(),
                diagnostics=({"severity": "error", "message": str(exc)},),
                artifacts=previous.artifacts,
                semantic=previous.semantic,
                execution_ir=previous.execution_ir,
                glyph04_views=previous.glyph04_views,
            )

        with self._lock:
            self._snapshot = snapshot
        return snapshot

    def save_source(self, source: str) -> StudioSnapshot:
        _atomic_write(self.input_path, source)
        return self.rebuild(source)

    def start_watching(self, interval: float = 0.35) -> None:
        if self._watcher is not None and self._watcher.is_alive():
            return
        self._stop.clear()

        def watch() -> None:
            last_seen = ""
            while not self._stop.wait(interval):
                try:
                    source = self.input_path.read_text(encoding="utf-8")
                except OSError as exc:
                    with self._lock:
                        current = self._snapshot
                        self._snapshot = StudioSnapshot(
                            version=current.version + 1,
                            status="error",
                            source=current.source,
                            digest=current.digest,
                            updated_at=_utc_now(),
                            diagnostics=(
                                {"severity": "error", "message": str(exc)},
                            ),
                            artifacts=current.artifacts,
                            semantic=current.semantic,
                            execution_ir=current.execution_ir,
                            glyph04_views=current.glyph04_views,
                        )
                    continue
                digest = _source_digest(source)
                if digest == last_seen:
                    continue
                last_seen = digest
                self.rebuild(source)

        self._watcher = threading.Thread(
            target=watch,
            name="glyph-studio-watch",
            daemon=True,
        )
        self._watcher.start()

    def stop(self) -> None:
        self._stop.set()
        if self._watcher is not None:
            self._watcher.join(timeout=1.0)

    def create_server(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> ThreadingHTTPServer:
        studio = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "GlyphStudio/1"

            def log_message(self, format: str, *args: object) -> None:
                return

            def _json(
                self,
                value: object,
                status: HTTPStatus = HTTPStatus.OK,
            ) -> None:
                payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)

            def _body(self) -> dict[str, Any]:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(length) if length else b"{}"
                    value = json.loads(raw.decode("utf-8"))
                    return value if isinstance(value, dict) else {}
                except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                    return {}

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    payload = STUDIO_HTML.encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                if parsed.path == "/api/state":
                    self._json(studio.state_dict())
                    return
                if parsed.path == "/api/artifact":
                    name = parse_qs(parsed.query).get("name", [""])[0]
                    artifact = studio.artifact(name)
                    if artifact is None:
                        self._json(
                            {"error": "unknown artifact"},
                            HTTPStatus.NOT_FOUND,
                        )
                    else:
                        self._json({"name": name, "content": artifact})
                    return
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                if self.path == "/api/save":
                    body = self._body()
                    source = body.get("source")
                    if not isinstance(source, str):
                        self._json(
                            {"error": "source must be text"},
                            HTTPStatus.BAD_REQUEST,
                        )
                        return
                    studio.save_source(source)
                    self._json(studio.state_dict())
                    return
                if self.path == "/api/rebuild":
                    studio.rebuild()
                    self._json(studio.state_dict())
                    return
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        return ThreadingHTTPServer((host, port), Handler)

    def serve(self, *, open_browser: bool = True) -> int:
        self.rebuild()
        self.start_watching()
        server = self.create_server(
            port=int(os.environ.get("GLYPH_STUDIO_PORT", "0"))
        )
        host, port = server.server_address[:2]
        url = f"http://{host}:{port}/"
        print(f"Glyph Studio: {url}")
        print(f"Source: {self.input_path}")
        print("終了: Ctrl+C")
        if open_browser and os.environ.get("GLYPH_STUDIO_NO_BROWSER") != "1":
            threading.Timer(0.15, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
            self.stop()
        return 0


def run_studio(input_path: str | Path) -> int:
    return GlyphStudio(input_path).serve()

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
import webbrowser

from .compiler import GlyphError
from .diagram_ui import DIAGRAM_HTML
from .incremental import IncrementalCompiler
from .io_state_views import build_io_state_views, empty_io_state_views


@dataclass(frozen=True)
class DiagramSnapshot:
    version: int
    status: str
    source: str
    digest: str
    updated_at: str
    diagnostics: tuple[dict[str, object], ...]
    views: dict[str, object]

    def to_dict(self, source_path: Path, output_path: Path) -> dict[str, object]:
        return {
            "version": self.version,
            "status": self.status,
            "source": self.source,
            "source_path": str(source_path),
            "output_path": str(output_path),
            "digest": self.digest,
            "updated_at": self.updated_at,
            "diagnostics": list(self.diagnostics),
            "views": self.views,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


class GlyphDiagramApp:
    """Compile one Glyph file and render generic I/O and state-machine diagrams."""

    def __init__(self, input_path: str | Path):
        self.input_path = Path(input_path).resolve()
        self.output_path = (
            self.input_path.parent
            / ".glyph"
            / self.input_path.stem
            / "io-state-views.json"
        )
        self.compiler = IncrementalCompiler()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._watcher: threading.Thread | None = None
        self._snapshot = DiagramSnapshot(
            version=0,
            status="starting",
            source="",
            digest="",
            updated_at=_utc_now(),
            diagnostics=(),
            views=empty_io_state_views(),
        )

    @property
    def snapshot(self) -> DiagramSnapshot:
        with self._lock:
            return self._snapshot

    def state_dict(self) -> dict[str, object]:
        with self._lock:
            return self._snapshot.to_dict(self.input_path, self.output_path)

    def rebuild(self, source: str | None = None) -> DiagramSnapshot:
        if source is None:
            source = self.input_path.read_text(encoding="utf-8")
        source_digest = _digest(source)
        previous = self.snapshot
        if previous.status == "ready" and previous.digest == source_digest:
            return previous

        try:
            result = self.compiler.compile_text(
                source,
                source_name=str(self.input_path),
                source_href=str(self.input_path),
            )
            compilation = result.snapshot
            views = build_io_state_views(
                compilation.model,
                compilation.diagrams.ir,
            )
            _atomic_write(
                self.output_path,
                json.dumps(views, ensure_ascii=False, indent=2) + "\n",
            )
            snapshot = DiagramSnapshot(
                version=previous.version + 1,
                status="ready",
                source=source,
                digest=source_digest,
                updated_at=_utc_now(),
                diagnostics=(),
                views=views,
            )
        except (GlyphError, OSError, ValueError) as exc:
            snapshot = DiagramSnapshot(
                version=previous.version + 1,
                status="error",
                source=source,
                digest=source_digest,
                updated_at=_utc_now(),
                diagnostics=({"severity": "error", "message": str(exc)},),
                views=previous.views,
            )

        with self._lock:
            self._snapshot = snapshot
        return snapshot

    def preview_source(self, source: str) -> DiagramSnapshot:
        return self.rebuild(source)

    def save_source(self, source: str) -> DiagramSnapshot:
        _atomic_write(self.input_path, source)
        return self.rebuild(source)

    def start_watching(self, interval: float = 0.35) -> None:
        if self._watcher is not None and self._watcher.is_alive():
            return
        self._stop.clear()
        try:
            last_seen = _digest(self.input_path.read_text(encoding="utf-8"))
        except OSError:
            last_seen = ""

        def watch() -> None:
            nonlocal last_seen
            while not self._stop.wait(interval):
                try:
                    source = self.input_path.read_text(encoding="utf-8")
                except OSError as exc:
                    with self._lock:
                        current = self._snapshot
                        self._snapshot = DiagramSnapshot(
                            version=current.version + 1,
                            status="error",
                            source=current.source,
                            digest=current.digest,
                            updated_at=_utc_now(),
                            diagnostics=(
                                {"severity": "error", "message": str(exc)},
                            ),
                            views=current.views,
                        )
                    continue
                current_digest = _digest(source)
                if current_digest == last_seen:
                    continue
                last_seen = current_digest
                self.rebuild(source)

        self._watcher = threading.Thread(
            target=watch,
            name="glyph-diagram-watch",
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
        app = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "GlyphDiagram/1"

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

            def _source(self) -> str | None:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(length) if length else b"{}"
                    body = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                    body = {}
                source = body.get("source") if isinstance(body, dict) else None
                if not isinstance(source, str):
                    self._json(
                        {"error": "source must be text"},
                        HTTPStatus.BAD_REQUEST,
                    )
                    return None
                return source

            def do_GET(self) -> None:
                if self.path == "/":
                    payload = DIAGRAM_HTML.encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                if self.path == "/api/state":
                    self._json(app.state_dict())
                    return
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                if self.path == "/api/preview":
                    source = self._source()
                    if source is not None:
                        app.preview_source(source)
                        self._json(app.state_dict())
                    return
                if self.path == "/api/save":
                    source = self._source()
                    if source is not None:
                        app.save_source(source)
                        self._json(app.state_dict())
                    return
                if self.path == "/api/rebuild":
                    app.rebuild()
                    self._json(app.state_dict())
                    return
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        return ThreadingHTTPServer((host, port), Handler)

    def serve(self, *, open_browser: bool = True) -> int:
        self.rebuild()
        self.start_watching()
        server = self.create_server(
            port=int(os.environ.get("GLYPH_DIAGRAM_PORT", "0"))
        )
        host, port = server.server_address[:2]
        url = f"http://{host}:{port}/"
        print(f"Glyph Diagram: {url}")
        print(f"Source: {self.input_path}")
        print("終了: Ctrl+C")
        if open_browser and os.environ.get("GLYPH_DIAGRAM_NO_BROWSER") != "1":
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


def run_diagram_app(input_path: str | Path) -> int:
    return GlyphDiagramApp(input_path).serve()

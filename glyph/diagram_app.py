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
from typing import Any, Callable
import webbrowser

from .compiler import GlyphError
from .diagram_ui import DIAGRAM_HTML
from .incremental import IncrementalCompiler
from .io_state_views import build_io_state_views, empty_io_state_views


ViewBuilder = Callable[[object, object], dict[str, object]]


class SaveConflictError(RuntimeError):
    """The source changed on disk after the editor loaded it."""

    def __init__(self, current_source: str, current_digest: str):
        super().__init__("source file changed outside Glyph Studio")
        self.current_source = current_source
        self.current_digest = current_digest


@dataclass(frozen=True)
class DiagramSnapshot:
    version: int
    status: str
    source: str
    digest: str
    rendered_digest: str
    last_successful_version: int
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
            "rendered_digest": self.rendered_digest,
            "last_successful_version": self.last_successful_version,
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

    def __init__(
        self,
        input_path: str | Path,
        *,
        view_builder: ViewBuilder = build_io_state_views,
    ):
        self.input_path = Path(input_path).resolve()
        self.output_path = (
            self.input_path.parent
            / ".glyph"
            / self.input_path.stem
            / "io-state-views.json"
        )
        self.compiler = IncrementalCompiler()
        self.view_builder = view_builder
        self._lock = threading.RLock()
        self._operation_lock = threading.RLock()
        self._stop = threading.Event()
        self._watcher: threading.Thread | None = None
        self._snapshot = DiagramSnapshot(
            version=0,
            status="starting",
            source="",
            digest="",
            rendered_digest="",
            last_successful_version=0,
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
        with self._operation_lock:
            if source is None:
                source = self.input_path.read_text(encoding="utf-8")
            source_digest = _digest(source)
            previous = self.snapshot
            if previous.status == "ready" and previous.digest == source_digest:
                return previous

            version = previous.version + 1
            try:
                result = self.compiler.compile_text(
                    source,
                    source_name=str(self.input_path),
                    source_href=str(self.input_path),
                )
                compilation = result.snapshot
                views = self.view_builder(
                    compilation.model,
                    compilation.diagrams.ir,
                )
                _atomic_write(
                    self.output_path,
                    json.dumps(views, ensure_ascii=False, indent=2) + "\n",
                )
                snapshot = DiagramSnapshot(
                    version=version,
                    status="ready",
                    source=source,
                    digest=source_digest,
                    rendered_digest=source_digest,
                    last_successful_version=version,
                    updated_at=_utc_now(),
                    diagnostics=(),
                    views=views,
                )
            except (GlyphError, OSError, ValueError) as exc:
                snapshot = DiagramSnapshot(
                    version=version,
                    status="error",
                    source=source,
                    digest=source_digest,
                    rendered_digest=previous.rendered_digest,
                    last_successful_version=previous.last_successful_version,
                    updated_at=_utc_now(),
                    diagnostics=({"severity": "error", "message": str(exc)},),
                    views=previous.views,
                )

            with self._lock:
                self._snapshot = snapshot
            return snapshot

    def save_source(
        self,
        source: str,
        *,
        base_digest: str | None = None,
        force: bool = False,
    ) -> DiagramSnapshot:
        with self._operation_lock:
            try:
                current_source = self.input_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                current_source = ""
            current_digest = _digest(current_source)
            if (
                base_digest is not None
                and not force
                and current_digest != base_digest
            ):
                raise SaveConflictError(current_source, current_digest)
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
                            rendered_digest=current.rendered_digest,
                            last_successful_version=current.last_successful_version,
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

            def _body(self) -> dict[str, Any] | None:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(length) if length else b"{}"
                    body: Any = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                    body = None
                if not isinstance(body, dict):
                    self._json(
                        {"error": "request body must be an object"},
                        HTTPStatus.BAD_REQUEST,
                    )
                    return None
                return body

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
                if self.path == "/api/save":
                    body = self._body()
                    if body is None:
                        return
                    source = body.get("source")
                    base_digest = body.get("base_digest")
                    force = body.get("force", False)
                    if not isinstance(source, str):
                        self._json(
                            {"error": "source must be text"},
                            HTTPStatus.BAD_REQUEST,
                        )
                        return
                    if base_digest is not None and not isinstance(base_digest, str):
                        self._json(
                            {"error": "base_digest must be text"},
                            HTTPStatus.BAD_REQUEST,
                        )
                        return
                    if not isinstance(force, bool):
                        self._json(
                            {"error": "force must be boolean"},
                            HTTPStatus.BAD_REQUEST,
                        )
                        return
                    try:
                        app.save_source(
                            source,
                            base_digest=base_digest,
                            force=force,
                        )
                    except SaveConflictError as exc:
                        self._json(
                            {
                                "error": "save_conflict",
                                "message": str(exc),
                                "current_source": exc.current_source,
                                "current_digest": exc.current_digest,
                                "state": app.state_dict(),
                            },
                            HTTPStatus.CONFLICT,
                        )
                        return
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


def run_diagram_app(
    input_path: str | Path,
    *,
    view_builder: ViewBuilder = build_io_state_views,
) -> int:
    return GlyphDiagramApp(input_path, view_builder=view_builder).serve()

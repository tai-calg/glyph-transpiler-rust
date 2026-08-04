from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import errno
import hashlib
import json
import os
from pathlib import Path
import threading
import uuid
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


class SaveWriteError(RuntimeError):
    """The source could not be persisted before compilation."""

    def __init__(
        self,
        code: str,
        message: str,
        status: HTTPStatus = HTTPStatus.INTERNAL_SERVER_ERROR,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class CompileRequest:
    operation_id: str
    source: str
    digest: str


@dataclass(frozen=True)
class DiagramSnapshot:
    version: int
    status: str
    source: str
    digest: str
    rendered_digest: str
    last_successful_version: int
    operation_id: str | None
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
            "operation_id": self.operation_id,
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
        self._compile_lock = threading.RLock()
        self._save_lock = threading.RLock()
        self._compile_condition = threading.Condition()
        self._pending_compile: CompileRequest | None = None
        self._compile_worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._watcher: threading.Thread | None = None
        self._snapshot = DiagramSnapshot(
            version=0,
            status="starting",
            source="",
            digest="",
            rendered_digest="",
            last_successful_version=0,
            operation_id=None,
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
        with self._compile_lock:
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
                    operation_id=None,
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
                    operation_id=None,
                    updated_at=_utc_now(),
                    diagnostics=({"severity": "error", "message": str(exc)},),
                    views=previous.views,
                )

            with self._lock:
                self._snapshot = snapshot
            return snapshot

    def _read_disk_source(self) -> str:
    try:
        return self.input_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except PermissionError as exc:
        raise SaveWriteError(
            "source_read_permission_denied",
            str(exc),
            HTTPStatus.FORBIDDEN,
        ) from exc
    except OSError as exc:
        raise SaveWriteError("source_read_failed", str(exc)) from exc

    def _persist_source(
        self,
        source: str,
        *,
        base_digest: str | None,
    ) -> str:
        current_source = self._read_disk_source()
        current_digest = _digest(current_source)
        if base_digest is not None and current_digest != base_digest:
            raise SaveConflictError(current_source, current_digest)
        try:
            _atomic_write(self.input_path, source)
        except PermissionError as exc:
            raise SaveWriteError(
                "save_permission_denied",
                str(exc),
                HTTPStatus.FORBIDDEN,
            ) from exc
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise SaveWriteError(
                    "save_no_space",
                    str(exc),
                    HTTPStatus.INSUFFICIENT_STORAGE,
                ) from exc
            raise SaveWriteError("save_io_error", str(exc)) from exc
        return _digest(source)

    def _publish_compiling(
        self,
        source: str,
        source_digest: str,
        operation_id: str,
    ) -> DiagramSnapshot:
        with self._lock:
            previous = self._snapshot
            snapshot = DiagramSnapshot(
                version=previous.version + 1,
                status="compiling",
                source=source,
                digest=source_digest,
                rendered_digest=previous.rendered_digest,
                last_successful_version=previous.last_successful_version,
                operation_id=operation_id,
                updated_at=_utc_now(),
                diagnostics=(),
                views=previous.views,
            )
            self._snapshot = snapshot
            return snapshot

    def _ensure_compile_worker(self) -> None:
        with self._compile_condition:
            if self._compile_worker is not None and self._compile_worker.is_alive():
                return
            self._compile_worker = threading.Thread(
                target=self._compile_loop,
                name="glyph-diagram-compile",
                daemon=True,
            )
            self._compile_worker.start()

    def _queue_compile(self, request: CompileRequest) -> None:
        self._ensure_compile_worker()
        with self._compile_condition:
            self._pending_compile = request
            self._compile_condition.notify_all()

    def _compile_loop(self) -> None:
        while True:
            with self._compile_condition:
                while self._pending_compile is None and not self._stop.is_set():
                    self._compile_condition.wait(timeout=0.5)
                if self._stop.is_set():
                    return
                request = self._pending_compile
                self._pending_compile = None
            assert request is not None
            self._compile_request(request)

    def _compile_request(self, request: CompileRequest) -> None:
        diagnostics: tuple[dict[str, object], ...] = ()
        views: dict[str, object] | None = None
        try:
            with self._compile_lock:
                result = self.compiler.compile_text(
                    request.source,
                    source_name=str(self.input_path),
                    source_href=str(self.input_path),
                )
                compilation = result.snapshot
                views = self.view_builder(
                    compilation.model,
                    compilation.diagrams.ir,
                )
        except (GlyphError, OSError, ValueError) as exc:
            diagnostics = ({"severity": "error", "message": str(exc)},)

        with self._lock:
            current = self._snapshot
            if current.operation_id != request.operation_id:
                return
            version = current.version + 1
            if views is not None:
                try:
                    _atomic_write(
                        self.output_path,
                        json.dumps(views, ensure_ascii=False, indent=2) + "
",
                    )
                except OSError as exc:
                    views = None
                    diagnostics = (
                        {
                            "severity": "error",
                            "message": f"artifact_write_failed: {exc}",
                        },
                    )
            if views is not None:
                self._snapshot = DiagramSnapshot(
                    version=version,
                    status="ready",
                    source=request.source,
                    digest=request.digest,
                    rendered_digest=request.digest,
                    last_successful_version=version,
                    operation_id=request.operation_id,
                    updated_at=_utc_now(),
                    diagnostics=(),
                    views=views,
                )
            else:
                self._snapshot = DiagramSnapshot(
                    version=version,
                    status="error",
                    source=request.source,
                    digest=request.digest,
                    rendered_digest=current.rendered_digest,
                    last_successful_version=current.last_successful_version,
                    operation_id=request.operation_id,
                    updated_at=_utc_now(),
                    diagnostics=diagnostics,
                    views=current.views,
                )

    def rebuild_async(self, source: str | None = None) -> DiagramSnapshot:
        if source is None:
            source = self._read_disk_source()
        source_digest = _digest(source)
        current = self.snapshot
        if current.digest == source_digest and current.status in {"ready", "compiling"}:
            return current
        operation_id = uuid.uuid4().hex
        snapshot = self._publish_compiling(
            source,
            source_digest,
            operation_id,
        )
        self._queue_compile(
            CompileRequest(operation_id, source, source_digest)
        )
        return snapshot

    def save_source_async(
        self,
        source: str,
        *,
        base_digest: str | None = None,
    ) -> DiagramSnapshot:
        with self._save_lock:
            source_digest = self._persist_source(
                source,
                base_digest=base_digest,
            )
            operation_id = uuid.uuid4().hex
            snapshot = self._publish_compiling(
                source,
                source_digest,
                operation_id,
            )
            self._queue_compile(
                CompileRequest(operation_id, source, source_digest)
            )
            return snapshot

    def save_source(
        self,
        source: str,
        *,
        base_digest: str | None = None,
    ) -> DiagramSnapshot:
        """Synchronous compatibility entrypoint for non-interactive callers."""
        with self._save_lock:
            self._persist_source(source, base_digest=base_digest)
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
                            operation_id=current.operation_id,
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
                current = self.snapshot
                if current.digest == current_digest and current.status == "compiling":
                    continue
                self.rebuild_async(source)

        self._watcher = threading.Thread(
            target=watch,
            name="glyph-diagram-watch",
            daemon=True,
        )
        self._watcher.start()

    def stop(self) -> None:
        self._stop.set()
        with self._compile_condition:
            self._compile_condition.notify_all()
        if self._watcher is not None:
            self._watcher.join(timeout=1.0)
        if self._compile_worker is not None:
            self._compile_worker.join(timeout=1.0)

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
            try:
                app.save_source_async(source, base_digest=base_digest)
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
            except SaveWriteError as exc:
                self._json(
                    {"error": exc.code, "message": str(exc)},
                    exc.status,
                )
                return
            self._json(app.state_dict(), HTTPStatus.ACCEPTED)
            return
        if self.path == "/api/rebuild":
            try:
                app.rebuild_async()
            except SaveWriteError as exc:
                self._json(
                    {"error": exc.code, "message": str(exc)},
                    exc.status,
                )
                return
            self._json(app.state_dict(), HTTPStatus.ACCEPTED)
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

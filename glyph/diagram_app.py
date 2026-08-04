from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import errno
import hashlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Callable
from urllib.parse import unquote, urlsplit
import uuid
import webbrowser

from .compiler import GlyphError
from .diagram_ui import DIAGRAM_HTML
from .incremental import IncrementalCompiler
from .io_state_views import build_io_state_views, empty_io_state_views


ViewBuilder = Callable[[object, object], dict[str, object]]
_SAVE_REQUEST_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_MAX_SAVE_OPERATIONS = 256


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

    def to_status_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "status": self.status,
            "digest": self.digest,
            "rendered_digest": self.rendered_digest,
            "last_successful_version": self.last_successful_version,
            "operation_id": self.operation_id,
            "updated_at": self.updated_at,
            "diagnostic_count": len(self.diagnostics),
        }

    def to_dict(self, source_path: Path, output_path: Path) -> dict[str, object]:
        return {
            **self.to_status_dict(),
            "source": self.source,
            "source_path": str(source_path),
            "output_path": str(output_path),
            "diagnostics": list(self.diagnostics),
            "views": self.views,
        }


@dataclass(frozen=True)
class SaveOperation:
    request_id: str
    status: str
    source_digest: str
    base_digest: str | None
    http_status: int
    operation_id: str | None = None
    error: str | None = None
    message: str | None = None
    current_source: str | None = None
    current_digest: str | None = None
    state: dict[str, object] | None = None
    updated_at: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "request_id": self.request_id,
            "status": self.status,
            "digest": self.source_digest,
            "base_digest": self.base_digest,
            "operation_id": self.operation_id,
            "updated_at": self.updated_at,
            "state": self.state,
        }
        if self.error is not None:
            payload["error"] = self.error
        if self.message is not None:
            payload["message"] = self.message
        if self.current_source is not None:
            payload["current_source"] = self.current_source
        if self.current_digest is not None:
            payload["current_digest"] = self.current_digest
        return payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _discard_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


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
        self._stopping = False
        self._watcher: threading.Thread | None = None
        self._save_operations: dict[str, SaveOperation] = {}
        self._save_operation_order: list[str] = []
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

    def status_dict(self) -> dict[str, object]:
        with self._lock:
            return self._snapshot.to_status_dict()

    def save_request_dict(self, request_id: str) -> dict[str, object] | None:
        with self._lock:
            operation = self._save_operations.get(request_id)
            if operation is None:
                return None
            payload = operation.to_dict()
            current = self._snapshot
            if (
                operation.status == "accepted"
                and operation.operation_id is not None
                and current.operation_id == operation.operation_id
            ):
                payload["state"] = current.to_status_dict()
            return payload

    def rebuild(self, source: str | None = None) -> DiagramSnapshot:
        """Synchronously rebuild for startup and non-interactive callers."""

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
                if not self._stopping:
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
    ) -> tuple[str, bool]:
        current_source = self._read_disk_source()
        current_digest = _digest(current_source)
        if base_digest is not None and current_digest != base_digest:
            raise SaveConflictError(current_source, current_digest)
        source_digest = _digest(source)
        if current_digest == source_digest:
            return source_digest, False
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
        return source_digest, True

    def _remember_save_operation(self, operation: SaveOperation) -> None:
        with self._lock:
            is_new = operation.request_id not in self._save_operations
            self._save_operations[operation.request_id] = operation
            if is_new:
                self._save_operation_order.append(operation.request_id)
            while len(self._save_operation_order) > _MAX_SAVE_OPERATIONS:
                expired = self._save_operation_order.pop(0)
                self._save_operations.pop(expired, None)

    def _existing_save_operation(
        self,
        request_id: str,
        source_digest: str,
        base_digest: str | None,
    ) -> SaveOperation | None:
        with self._lock:
            existing = self._save_operations.get(request_id)
        if existing is None:
            return None
        if (
            existing.source_digest == source_digest
            and existing.base_digest == base_digest
        ):
            return existing
        return SaveOperation(
            request_id=request_id,
            status="error",
            source_digest=source_digest,
            base_digest=base_digest,
            http_status=int(HTTPStatus.CONFLICT),
            error="save_request_mismatch",
            message="request_id was already used for different save content",
            state=self.status_dict(),
            updated_at=_utc_now(),
        )

    def _publish_compiling(
        self,
        source: str,
        source_digest: str,
        operation_id: str,
    ) -> DiagramSnapshot:
        with self._lock:
            if self._stopping:
                raise SaveWriteError(
                    "server_stopping",
                    "Glyph Studio is stopping",
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
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
        with self._lock:
            if self._stopping:
                return
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
        with self._lock:
            if self._stopping:
                return
        self._ensure_compile_worker()
        with self._compile_condition:
            if self._stop.is_set():
                return
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
            try:
                self._compile_request(request)
            except Exception as exc:
                self._publish_compile_error(
                    request,
                    "internal_compile_error",
                    f"{type(exc).__name__}: {exc}",
                )

    def _publish_compile_error(
        self,
        request: CompileRequest,
        code: str,
        message: str,
    ) -> None:
        with self._lock:
            current = self._snapshot
            if self._stopping or current.operation_id != request.operation_id:
                return
            self._snapshot = DiagramSnapshot(
                version=current.version + 1,
                status="error",
                source=request.source,
                digest=request.digest,
                rendered_digest=current.rendered_digest,
                last_successful_version=current.last_successful_version,
                operation_id=request.operation_id,
                updated_at=_utc_now(),
                diagnostics=(
                    {
                        "severity": "error",
                        "code": code,
                        "message": message,
                    },
                ),
                views=current.views,
            )

    def _compile_request(self, request: CompileRequest) -> None:
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
            self._publish_compile_error(request, "compile_error", str(exc))
            return

        artifact = json.dumps(views, ensure_ascii=False, indent=2) + "\n"
        temporary = self.output_path.with_name(
            f".{self.output_path.name}.{request.operation_id}.tmp"
        )
        try:
            temporary.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(artifact, encoding="utf-8")
        except OSError as exc:
            _discard_file(temporary)
            self._publish_compile_error(
                request,
                "artifact_write_failed",
                str(exc),
            )
            return

        with self._lock:
            current = self._snapshot
            if (
                self._stopping
                or current.operation_id != request.operation_id
            ):
                _discard_file(temporary)
                return
            version = current.version + 1
            try:
                temporary.replace(self.output_path)
            except OSError as exc:
                _discard_file(temporary)
                self._snapshot = DiagramSnapshot(
                    version=version,
                    status="error",
                    source=request.source,
                    digest=request.digest,
                    rendered_digest=current.rendered_digest,
                    last_successful_version=current.last_successful_version,
                    operation_id=request.operation_id,
                    updated_at=_utc_now(),
                    diagnostics=(
                        {
                            "severity": "error",
                            "code": "artifact_publish_failed",
                            "message": str(exc),
                        },
                    ),
                    views=current.views,
                )
                return
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
        self._queue_compile(CompileRequest(operation_id, source, source_digest))
        return snapshot

    def submit_save(
        self,
        source: str,
        *,
        base_digest: str | None = None,
        request_id: str | None = None,
    ) -> SaveOperation:
        selected_request_id = request_id or uuid.uuid4().hex
        source_digest = _digest(source)
        if not _SAVE_REQUEST_PATTERN.fullmatch(selected_request_id):
            return SaveOperation(
                request_id=selected_request_id,
                status="error",
                source_digest=source_digest,
                base_digest=base_digest,
                http_status=int(HTTPStatus.BAD_REQUEST),
                error="invalid_save_request_id",
                message="request_id must contain only letters, numbers, dot, dash, or underscore",
                state=self.status_dict(),
                updated_at=_utc_now(),
            )

        existing = self._existing_save_operation(
            selected_request_id,
            source_digest,
            base_digest,
        )
        if existing is not None:
            return existing

        saving = SaveOperation(
            request_id=selected_request_id,
            status="saving",
            source_digest=source_digest,
            base_digest=base_digest,
            http_status=int(HTTPStatus.ACCEPTED),
            state=self.status_dict(),
            updated_at=_utc_now(),
        )
        self._remember_save_operation(saving)

        try:
            with self._save_lock:
                source_digest, _written = self._persist_source(
                    source,
                    base_digest=base_digest,
                )
                current = self.snapshot
                if (
                    current.digest == source_digest
                    and current.status in {"ready", "compiling"}
                ):
                    snapshot = current
                else:
                    snapshot = self._publish_compiling(
                        source,
                        source_digest,
                        selected_request_id,
                    )
                    self._queue_compile(
                        CompileRequest(
                            selected_request_id,
                            source,
                            source_digest,
                        )
                    )
            accepted = replace(
                saving,
                status="accepted",
                source_digest=source_digest,
                operation_id=snapshot.operation_id,
                state=snapshot.to_status_dict(),
                updated_at=_utc_now(),
            )
            self._remember_save_operation(accepted)
            return accepted
        except SaveConflictError as exc:
            conflict = replace(
                saving,
                status="conflict",
                http_status=int(HTTPStatus.CONFLICT),
                error="save_conflict",
                message=str(exc),
                current_source=exc.current_source,
                current_digest=exc.current_digest,
                state=self.status_dict(),
                updated_at=_utc_now(),
            )
            self._remember_save_operation(conflict)
            return conflict
        except SaveWriteError as exc:
            failed = replace(
                saving,
                status="error",
                http_status=int(exc.status),
                error=exc.code,
                message=str(exc),
                state=self.status_dict(),
                updated_at=_utc_now(),
            )
            self._remember_save_operation(failed)
            return failed

    def save_source_async(
        self,
        source: str,
        *,
        base_digest: str | None = None,
    ) -> DiagramSnapshot:
        operation = self.submit_save(source, base_digest=base_digest)
        if operation.status == "conflict":
            raise SaveConflictError(
                operation.current_source or "",
                operation.current_digest or "",
            )
        if operation.status == "error":
            raise SaveWriteError(
                operation.error or "save_error",
                operation.message or "save failed",
                HTTPStatus(operation.http_status),
            )
        return self.snapshot

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
        with self._lock:
            if self._stopping:
                return
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
                        if self._stopping:
                            return
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
        with self._lock:
            self._stopping = True
        self._stop.set()
        with self._compile_condition:
            self._pending_compile = None
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
                path = urlsplit(self.path).path
                if path == "/":
                    payload = DIAGRAM_HTML.encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                if path == "/api/state":
                    self._json(app.state_dict())
                    return
                if path == "/api/status":
                    self._json(app.status_dict())
                    return
                if path.startswith("/api/save-status/"):
                    request_id = unquote(path.removeprefix("/api/save-status/"))
                    operation = app.save_request_dict(request_id)
                    if operation is None:
                        self._json(
                            {"error": "save_request_not_found"},
                            HTTPStatus.NOT_FOUND,
                        )
                    else:
                        self._json(operation)
                    return
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                path = urlsplit(self.path).path
                if path == "/api/save":
                    body = self._body()
                    if body is None:
                        return
                    source = body.get("source")
                    base_digest = body.get("base_digest")
                    request_id = body.get("request_id")
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
                    if request_id is not None and not isinstance(request_id, str):
                        self._json(
                            {"error": "request_id must be text"},
                            HTTPStatus.BAD_REQUEST,
                        )
                        return
                    operation = app.submit_save(
                        source,
                        base_digest=base_digest,
                        request_id=request_id,
                    )
                    self._json(
                        operation.to_dict(),
                        HTTPStatus(operation.http_status),
                    )
                    return
                if path == "/api/rebuild":
                    try:
                        snapshot = app.rebuild_async()
                    except SaveWriteError as exc:
                        self._json(
                            {"error": exc.code, "message": str(exc)},
                            exc.status,
                        )
                        return
                    self._json(snapshot.to_status_dict(), HTTPStatus.ACCEPTED)
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

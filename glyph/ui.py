from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .compilation import CompilationPipeline
from .incremental import IncrementalCompiler
from .pure_runtime import InvocationResult, LivePureGlyphRuntime
from .ui_backends import BackendRegistry, default_backend_registry
from .ui_ir import UiApplication, build_ui_application
from .ui_schema import (
    dump_ui_application,
    dumps_ui_application,
    fingerprint_ui_application,
    validate_ui_application,
)


UI_API_VERSION = 1


class UiProjectError(RuntimeError):
    """Raised when a public UI project cannot be compiled, refreshed, or rebuilt."""


@dataclass(frozen=True)
class UiSchemaState:
    """Result of comparing the running component schema with the latest source schema."""

    active_fingerprint: str
    candidate_fingerprint: str
    changed: bool
    requires_restart: bool
    candidate: UiApplication


class UiProject:
    """Public lifecycle owner for one file-backed Glyph UI application.

    UiProject keeps compiler, Live Image, UI IR, and backend selection behind one stable
    facade. Function-body edits continue through LivePureGlyphRuntime without rebuilding
    the component graph. Signature/type edits are reported as a pending schema and require
    an explicit restart so browser components and the active World cannot silently diverge.
    """

    def __init__(
        self,
        source_path: Path,
        runtime: LivePureGlyphRuntime,
        application: UiApplication,
        *,
        function_name: str | None,
        title: str | None,
        registry: BackendRegistry,
    ) -> None:
        validate_ui_application(application)
        self._source_path = source_path
        self._runtime = runtime
        self._application = application
        self._function_name = function_name
        self._title = title
        self._registry = registry
        self._fingerprint = fingerprint_ui_application(application)
        self._pending_application: UiApplication | None = None
        self._closed = False
        self._watching = False

    @classmethod
    def open(
        cls,
        source_path: str | Path,
        *,
        function_name: str | None = None,
        title: str | None = None,
        compiler: IncrementalCompiler | None = None,
        registry: BackendRegistry | None = None,
    ) -> "UiProject":
        path = Path(source_path).resolve()
        runtime = LivePureGlyphRuntime(path, compiler=compiler)
        try:
            snapshot = runtime.compiler.last_snapshot
            if snapshot is None:
                raise UiProjectError("compiler produced no initial snapshot")
            application = build_ui_application(
                snapshot.model,
                function_name=function_name,
                source_name=str(path),
                title=title,
            )
            return cls(
                path,
                runtime,
                application,
                function_name=function_name,
                title=title,
                registry=registry or default_backend_registry(),
            )
        except Exception:
            runtime.stop()
            raise

    @property
    def source_path(self) -> Path:
        return self._source_path

    @property
    def source_text(self) -> str:
        self._ensure_open()
        return self._runtime.source_text

    @property
    def application(self) -> UiApplication:
        self._ensure_open()
        return self._application

    @property
    def runtime(self) -> LivePureGlyphRuntime:
        """Return the current runtime for backend authors needing World-level integration."""

        self._ensure_open()
        return self._runtime

    @property
    def schema_fingerprint(self) -> str:
        return self._fingerprint

    @property
    def pending_application(self) -> UiApplication | None:
        return self._pending_application

    @property
    def requires_restart(self) -> bool:
        return self._pending_application is not None

    @property
    def backend_names(self) -> tuple[str, ...]:
        return self._registry.names()

    def ui_ir(self) -> dict[str, object]:
        self._ensure_open()
        return dump_ui_application(self._application)

    def ui_ir_json(self) -> str:
        self._ensure_open()
        return dumps_ui_application(self._application)

    def invoke(self, arguments: dict[str, Any], *, refresh: bool = True) -> InvocationResult:
        self._ensure_open()
        return self._runtime.invoke(
            self._application.action.name,
            arguments,
            refresh=refresh,
        )

    def state_dict(self) -> dict[str, object]:
        self._ensure_open()
        state = self._runtime.state_dict()
        state["ui"] = {
            "api_version": UI_API_VERSION,
            "schema": self._application.to_dict(),
            "schema_fingerprint": self._fingerprint,
            "requires_restart": self.requires_restart,
            "pending_schema_fingerprint": (
                fingerprint_ui_application(self._pending_application)
                if self._pending_application is not None
                else None
            ),
        }
        return state

    def inspect_schema(self, *, force: bool = False) -> UiSchemaState:
        """Compile the latest source and report whether the component graph changed."""

        self._ensure_open()
        self._runtime.refresh(force=force)
        snapshot = self._runtime.compiler.last_snapshot
        if snapshot is None:
            raise UiProjectError("compiler produced no snapshot while inspecting UI schema")
        candidate = build_ui_application(
            snapshot.model,
            function_name=self._function_name,
            source_name=str(self._source_path),
            title=self._title,
        )
        validate_ui_application(candidate)
        candidate_fingerprint = fingerprint_ui_application(candidate)
        changed = candidate_fingerprint != self._fingerprint
        if changed:
            self._pending_application = candidate
        else:
            self._application = candidate
            self._pending_application = None
        return UiSchemaState(
            active_fingerprint=self._fingerprint,
            candidate_fingerprint=candidate_fingerprint,
            changed=changed,
            requires_restart=changed,
            candidate=candidate,
        )

    def restart(self) -> UiApplication:
        """Recreate runtime and UI schema from the current file after an explicit decision."""

        self._ensure_open()
        was_watching = self._watching
        old_runtime = self._runtime
        new_runtime = LivePureGlyphRuntime(self._source_path)
        try:
            snapshot = new_runtime.compiler.last_snapshot
            if snapshot is None:
                raise UiProjectError("compiler produced no snapshot during UI restart")
            application = build_ui_application(
                snapshot.model,
                function_name=self._function_name,
                source_name=str(self._source_path),
                title=self._title,
            )
            validate_ui_application(application)
        except Exception:
            new_runtime.stop()
            raise
        self._runtime = new_runtime
        self._application = application
        self._fingerprint = fingerprint_ui_application(application)
        self._pending_application = None
        self._watching = False
        old_runtime.stop()
        if was_watching:
            self.start_watching()
        return application

    def build(self, backend: str = "gradio", **options: Any) -> Any:
        self._ensure_open()
        return self._registry.create(backend).build(self, **options)

    def launch(self, backend: str = "gradio", **options: Any) -> Any:
        self._ensure_open()
        return self._registry.create(backend).launch(self, **options)

    def start_watching(self, interval: float = 0.35) -> None:
        self._ensure_open()
        self._runtime.start_watching(interval)
        self._watching = True

    def close(self) -> None:
        if self._closed:
            return
        self._runtime.stop()
        self._closed = True
        self._watching = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise UiProjectError("UI project is closed")

    def __enter__(self) -> "UiProject":
        self._ensure_open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


def compile_ui_source(
    source: str,
    *,
    function_name: str | None = None,
    source_name: str = "input.glyph",
    title: str | None = None,
) -> UiApplication:
    """Compile source text into validated, backend-neutral glyph.ui-ir."""

    compilation = CompilationPipeline().compile_text(source, source_name=source_name)
    application = build_ui_application(
        compilation.model,
        function_name=function_name,
        source_name=source_name,
        title=title,
    )
    validate_ui_application(application)
    return application


def compile_ui_file(
    source_path: str | Path,
    *,
    function_name: str | None = None,
    title: str | None = None,
) -> UiApplication:
    path = Path(source_path).resolve()
    return compile_ui_source(
        path.read_text(encoding="utf-8"),
        function_name=function_name,
        source_name=str(path),
        title=title,
    )


def open_ui(
    source_path: str | Path,
    *,
    function_name: str | None = None,
    title: str | None = None,
    compiler: IncrementalCompiler | None = None,
    registry: BackendRegistry | None = None,
) -> UiProject:
    return UiProject.open(
        source_path,
        function_name=function_name,
        title=title,
        compiler=compiler,
        registry=registry,
    )


__all__ = [
    "UI_API_VERSION",
    "UiProject",
    "UiProjectError",
    "UiSchemaState",
    "compile_ui_file",
    "compile_ui_source",
    "open_ui",
]

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .pure_runtime import LivePureGlyphRuntime
from .ui_ir import UiApplication, build_ui_application
from .ui_manifest import UiManifest, apply_ui_manifest, load_ui_manifest


class UiRenderer(Protocol):
    """Public renderer contract for projecting a UiApplication into a frontend."""

    def __call__(
        self,
        runtime: LivePureGlyphRuntime,
        application: UiApplication,
        **options: Any,
    ) -> Any: ...


class RendererRegistry:
    """Explicit renderer registry. Registration never imports optional frontends eagerly."""

    def __init__(self) -> None:
        self._renderers: dict[str, UiRenderer] = {}

    def register(self, name: str, renderer: UiRenderer, *, replace: bool = False) -> None:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("renderer name must not be empty")
        if normalized in self._renderers and not replace:
            raise ValueError(f"renderer '{normalized}' is already registered")
        self._renderers[normalized] = renderer

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._renderers))

    def get(self, name: str) -> UiRenderer:
        normalized = name.strip().lower()
        renderer = self._renderers.get(normalized)
        if renderer is None:
            available = ", ".join(self.names()) or "none"
            raise ValueError(f"unknown renderer '{name}'; available: {available}")
        return renderer


renderers = RendererRegistry()


def _load_gradio_renderer(
    runtime: LivePureGlyphRuntime,
    application: UiApplication,
    **options: Any,
) -> Any:
    try:
        from .gradio_renderer import build_gradio_app
    except ModuleNotFoundError as exc:
        if exc.name in {"gradio", "pandas"}:
            raise RuntimeError(
                "Gradio renderer dependencies are missing; install glyph-rust[ui]"
            ) from exc
        raise
    return build_gradio_app(runtime, application, **options)


renderers.register("gradio", _load_gradio_renderer)


@dataclass
class GlyphUiProject:
    """Public, lifecycle-owning facade for one compiled Glyph UI application."""

    source_path: Path
    runtime: LivePureGlyphRuntime
    application: UiApplication
    manifest: UiManifest | None = None

    def render(self, renderer: str = "gradio", **options: Any) -> Any:
        return renderers.get(renderer)(self.runtime, self.application, **options)

    def ui_ir_json(self) -> str:
        return self.application.to_json()

    def start_watching(self, interval: float = 0.35) -> None:
        self.runtime.start_watching(interval)

    def close(self) -> None:
        self.runtime.stop()

    def __enter__(self) -> "GlyphUiProject":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


def open_ui_project(
    source: str | Path,
    *,
    function: str | None = None,
    title: str | None = None,
    manifest: str | Path | UiManifest | None = None,
) -> GlyphUiProject:
    """Compile a Glyph source and return the stable public UI facade.

    The optional manifest may alter presentation metadata only. It cannot inject Python
    callbacks, effect implementations, imports, or arbitrary code.
    """

    source_path = Path(source).resolve()
    loaded_manifest: UiManifest | None
    if manifest is None:
        loaded_manifest = None
    elif isinstance(manifest, UiManifest):
        loaded_manifest = manifest
    else:
        loaded_manifest = load_ui_manifest(manifest)

    selected_function = function
    if selected_function is None and loaded_manifest is not None:
        selected_function = loaded_manifest.function

    runtime = LivePureGlyphRuntime(source_path)
    try:
        snapshot = runtime.compiler.last_snapshot
        if snapshot is None:
            raise RuntimeError("compiler produced no snapshot")
        application = build_ui_application(
            snapshot.model,
            function_name=selected_function,
            source_name=str(source_path),
            title=title,
        )
        if loaded_manifest is not None:
            application = apply_ui_manifest(application, loaded_manifest)
        return GlyphUiProject(source_path, runtime, application, loaded_manifest)
    except Exception:
        runtime.stop()
        raise


__all__ = [
    "GlyphUiProject",
    "RendererRegistry",
    "UiRenderer",
    "open_ui_project",
    "renderers",
]

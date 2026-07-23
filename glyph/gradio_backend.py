from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import gradio as gr

from .gradio_renderer import GENERIC_GRADIO_CSS, build_gradio_app
from .ui_backends import BACKEND_API_VERSION


@dataclass(frozen=True)
class GradioOptions:
    """Stable launch options for the built-in Gradio backend."""

    server_name: str = "127.0.0.1"
    server_port: int = 7860
    inbrowser: bool = True
    share: bool = False
    watch: bool = True
    watch_interval: float = 0.35
    theme: Any = None
    css: str | None = None
    launch_kwargs: dict[str, Any] = field(default_factory=dict)


class GradioBackend:
    """Built-in glyph.ui backend implemented with Gradio 6."""

    name = "gradio"
    api_version = BACKEND_API_VERSION

    def build(self, project: Any, **options: Any) -> gr.Blocks:
        unknown = set(options) - {"options"}
        if unknown:
            raise TypeError(
                "GradioBackend.build accepts only options=GradioOptions; unknown: "
                + ", ".join(sorted(unknown))
            )
        configured = options.get("options")
        if configured is not None and not isinstance(configured, GradioOptions):
            raise TypeError("options must be a GradioOptions value")
        return build_gradio_app(project.runtime, project.application)

    def launch(self, project: Any, **options: Any) -> Any:
        configured = options.pop("options", None)
        if configured is None:
            configured = GradioOptions(**options)
        elif options:
            raise TypeError("pass either options=GradioOptions or keyword launch options")
        if not isinstance(configured, GradioOptions):
            raise TypeError("options must be a GradioOptions value")
        if configured.watch:
            project.start_watching(configured.watch_interval)
        demo = build_gradio_app(project.runtime, project.application)
        launch_kwargs = dict(configured.launch_kwargs)
        launch_kwargs.setdefault("server_name", configured.server_name)
        launch_kwargs.setdefault("server_port", configured.server_port)
        launch_kwargs.setdefault("inbrowser", configured.inbrowser)
        launch_kwargs.setdefault("share", configured.share)
        launch_kwargs.setdefault("theme", configured.theme or gr.themes.Ocean())
        launch_kwargs.setdefault("css", configured.css or GENERIC_GRADIO_CSS)
        return demo.launch(**launch_kwargs)


__all__ = ["GradioBackend", "GradioOptions"]

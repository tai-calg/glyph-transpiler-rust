from __future__ import annotations

from pathlib import Path

from . import diagram_app
from .failure_result_labels import enhance_failure_result_html
from .initial_transition_layout import enhance_initial_transition_html
from .transition_label_layout import enhance_diagram_html
from .transition_route_labels import enhance_transition_route_html
from .transition_semantics_runtime import enrich_runtime_io_state_views
from .uml_transition_layout import enhance_uml_transition_html


_BASE_BUILD_IO_STATE_VIEWS = diagram_app.build_io_state_views


def _build_semantic_views(model, execution):
    return enrich_runtime_io_state_views(
        model,
        _BASE_BUILD_IO_STATE_VIEWS(model, execution),
    )


def run_diagram_app(input_path: str | Path) -> int:
    """Run the diagram app with UML semantics and collision-free initial routing."""

    diagram_app.build_io_state_views = _build_semantic_views
    diagram_app.DIAGRAM_HTML = enhance_failure_result_html(
        enhance_initial_transition_html(
            enhance_transition_route_html(
                enhance_uml_transition_html(
                    enhance_diagram_html(diagram_app.DIAGRAM_HTML)
                )
            )
        )
    )
    return diagram_app.run_diagram_app(input_path)

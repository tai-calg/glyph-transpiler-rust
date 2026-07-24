from __future__ import annotations

from pathlib import Path

from . import diagram_app
from .initial_transition_layout import enhance_initial_transition_html
from .transition_label_layout import enhance_diagram_html
from .transition_route_labels import enhance_transition_route_html
from .uml_transition_layout import enhance_uml_transition_html


def run_diagram_app(input_path: str | Path) -> int:
    """Run the diagram app from compiler-produced StateTransitionIR v2."""

    diagram_app.DIAGRAM_HTML = enhance_initial_transition_html(
        enhance_transition_route_html(
            enhance_uml_transition_html(
                enhance_diagram_html(diagram_app.DIAGRAM_HTML)
            )
        )
    )
    return diagram_app.run_diagram_app(input_path)

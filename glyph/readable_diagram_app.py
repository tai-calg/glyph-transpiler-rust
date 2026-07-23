from __future__ import annotations

from pathlib import Path

from . import diagram_app
from .transition_label_layout import enhance_diagram_html


def run_diagram_app(input_path: str | Path) -> int:
    """Run the standard diagram app with the adaptive transition-label layer."""

    diagram_app.DIAGRAM_HTML = enhance_diagram_html(diagram_app.DIAGRAM_HTML)
    return diagram_app.run_diagram_app(input_path)

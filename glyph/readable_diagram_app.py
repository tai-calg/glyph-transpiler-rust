from __future__ import annotations

from pathlib import Path

from . import diagram_app
from .code_derived_system_ui import enhance_code_derived_system_html
from .diagram_editor_exports import enhance_diagram_editor_exports_html
from .diagram_editor_render_guard import enhance_diagram_editor_render_guard_html
from .diagram_editor_route_guard import enhance_diagram_editor_route_guard_html
from .diagram_label_editor import enhance_diagram_label_editor_html
from .diagram_live_stability import (
    enhance_diagram_live_stability_html,
    install_serial_compilation,
)
from .diagram_workspace_layout import enhance_workspace_layout_html
from .initial_transition_layout import enhance_initial_transition_html
from .state_transition_ir_renderer import enhance_state_transition_ir_html
from .transition_label_layout import enhance_diagram_html
from .transition_route_labels import enhance_transition_route_html
from .uml_transition_layout import enhance_uml_transition_html


def prepare_diagram_app() -> None:
    """Install the shared compiler and browser presentation layers once per process."""

    install_serial_compilation()
    diagram_app.DIAGRAM_HTML = enhance_workspace_layout_html(
        enhance_diagram_label_editor_html(
            enhance_diagram_live_stability_html(
                enhance_code_derived_system_html(
                    enhance_diagram_editor_render_guard_html(
                        enhance_diagram_editor_route_guard_html(
                            enhance_diagram_editor_exports_html(
                                enhance_state_transition_ir_html(
                                    enhance_initial_transition_html(
                                        enhance_transition_route_html(
                                            enhance_uml_transition_html(
                                                enhance_diagram_html(
                                                    diagram_app.DIAGRAM_HTML
                                                )
                                            )
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
            )
        )
    )


def run_diagram_app(input_path: str | Path) -> int:
    """Run the editable diagram app from compiler-produced StateTransitionIR v2."""

    prepare_diagram_app()
    return diagram_app.run_diagram_app(input_path)

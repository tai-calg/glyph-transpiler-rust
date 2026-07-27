from __future__ import annotations

from pathlib import Path

from . import diagram_app
from .code_derived_system_ui import enhance_code_derived_system_html
from .diagnostic_i18n import localize_message_payload
from .diagram_canvas_navigation import enhance_diagram_canvas_navigation_html
from .diagram_canvas_viewport import enhance_diagram_canvas_viewport_html
from .diagram_editor_exports import enhance_diagram_editor_exports_html
from .diagram_editor_render_guard import enhance_diagram_editor_render_guard_html
from .diagram_editor_route_guard import enhance_diagram_editor_route_guard_html
from .diagram_label_editor import enhance_diagram_label_editor_html
from .diagram_live_stability import (
    enhance_diagram_live_stability_html,
    install_serial_compilation,
)
from .diagram_locale import enhance_diagram_locale_html
from .diagram_workspace_layout import enhance_workspace_layout_html
from .initial_transition_layout import enhance_initial_transition_html
from .state_transition_ir_renderer import enhance_state_transition_ir_html
from .transition_io_clusters import enhance_transition_io_clusters_html
from .transition_io_collision_solver import enhance_transition_io_collision_solver_html
from .transition_label_layout import enhance_diagram_html
from .transition_label_readability import enhance_transition_label_readability_html
from .transition_route_labels import enhance_transition_route_html
from .uml_transition_layout import enhance_uml_transition_html


def _install_diagram_diagnostic_localization() -> None:
    """Expose canonical, Japanese, and English diagnostic text in API state."""

    original = diagram_app.DiagramSnapshot.to_dict
    if getattr(original, "__glyph_localized__", False):
        return

    def localized(self, source_path, output_path, _original=original):
        return localize_message_payload(_original(self, source_path, output_path))

    localized.__glyph_localized__ = True
    diagram_app.DiagramSnapshot.to_dict = localized


def prepare_diagram_app() -> None:
    """Install the shared compiler and browser presentation layers once per process."""

    install_serial_compilation()
    _install_diagram_diagnostic_localization()
    diagram_app.DIAGRAM_HTML = enhance_transition_label_readability_html(
        enhance_diagram_locale_html(
            enhance_transition_io_collision_solver_html(
                enhance_transition_io_clusters_html(
                    enhance_diagram_canvas_viewport_html(
                        enhance_diagram_canvas_navigation_html(
                            enhance_workspace_layout_html(
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
                        )
                    )
                )
            )
        )
    )


def run_diagram_app(input_path: str | Path) -> int:
    """Run the editable diagram app from compiler-produced StateTransitionIR v3."""

    prepare_diagram_app()
    return diagram_app.run_diagram_app(input_path)

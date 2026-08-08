from __future__ import annotations

from pathlib import Path

from . import diagram_app
from .adaptive_state_focus import enhance_adaptive_state_focus_html
from .code_derived_system_ui import enhance_code_derived_system_html
from .diagnostic_i18n import localize_message_payload
from .diagram_canvas_navigation import enhance_diagram_canvas_navigation_html
from .diagram_canvas_viewport import enhance_diagram_canvas_viewport_html
from .diagram_editor_exports import enhance_diagram_editor_exports_html
from .diagram_editor_render_guard import enhance_diagram_editor_render_guard_html
from .diagram_editor_route_guard import enhance_diagram_editor_route_guard_html
from .diagram_geometry_kernel import enhance_diagram_geometry_kernel_html
from .diagram_label_editor import enhance_diagram_label_editor_html
from .diagram_live_stability import (
    enhance_diagram_live_stability_html,
    install_serial_compilation,
)
from .diagram_locale import enhance_diagram_locale_html
from .diagram_middle_drag_zoom import enhance_diagram_middle_drag_zoom_html
from .diagram_rendered_geometry_adapter import enhance_diagram_rendered_geometry_html
from .diagram_save_controller import enhance_save_controller_html
from .diagram_save_presentation import enhance_save_presentation_html
from .diagram_workspace_layout import enhance_workspace_layout_html
from .editor_identifier_highlight import enhance_editor_identifier_highlight_html
from .state_diagram_workspace import enhance_state_diagram_workspace_html
from .state_viewport_reservation import enhance_state_viewport_reservation_html
from .transition_arrow_clearance import enhance_transition_arrow_clearance_html
from .transition_enabling_case_rendering import (
    enhance_transition_enabling_case_rendering_html,
)
from .transition_execution_context_selector import (
    enhance_transition_execution_context_selector_html,
)
from .transition_io_canonicalizer import enhance_transition_io_canonicalizer_html
from .transition_io_clusters import enhance_transition_io_clusters_html
from .transition_label_drag_guard import enhance_transition_label_drag_guard_html
from .transition_label_inspector import enhance_transition_label_inspector_html
from .transition_layout_interaction_adapter import (
    enhance_transition_layout_interaction_adapter_html,
)
from .transition_layout_tab_guard import enhance_transition_layout_tab_guard_html
from .transition_layout_transaction import enhance_transition_layout_transaction_html
from .transition_node_layout_guard import enhance_transition_node_layout_guard_html
from .transition_node_position_adapter import (
    enhance_transition_node_position_adapter_html,
)
from .transition_readable_exports import enhance_transition_readable_exports_html
from .transition_readable_layout import enhance_transition_readable_layout_html
from .transition_semantic_status_ui import enhance_transition_semantic_status_ui_html


def _install_diagram_diagnostic_localization() -> None:
    """Expose canonical, Japanese, and English diagnostic text in API state."""

    original = diagram_app.DiagramSnapshot.to_dict
    if getattr(original, "__glyph_localized__", False):
        return

    def localized(self, source_path, output_path, _original=original):
        return localize_message_payload(_original(self, source_path, output_path))

    localized.__glyph_localized__ = True
    diagram_app.DiagramSnapshot.to_dict = localized


def _presentation_pipeline():
    """Return the ordinary, event-driven state-diagram presentation pipeline."""

    return (
        enhance_diagram_geometry_kernel_html,
        enhance_diagram_rendered_geometry_html,
        enhance_diagram_editor_exports_html,
        enhance_diagram_editor_route_guard_html,
        enhance_diagram_editor_render_guard_html,
        enhance_code_derived_system_html,
        enhance_diagram_live_stability_html,
        enhance_editor_identifier_highlight_html,
        enhance_diagram_label_editor_html,
        enhance_workspace_layout_html,
        enhance_state_viewport_reservation_html,
        enhance_diagram_canvas_navigation_html,
        enhance_diagram_canvas_viewport_html,
        enhance_diagram_middle_drag_zoom_html,
        enhance_state_diagram_workspace_html,
        enhance_transition_arrow_clearance_html,
        enhance_diagram_locale_html,
        enhance_transition_execution_context_selector_html,
        enhance_transition_node_position_adapter_html,
        enhance_transition_io_clusters_html,
        enhance_transition_io_canonicalizer_html,
        enhance_transition_enabling_case_rendering_html,
        enhance_transition_node_layout_guard_html,
        enhance_transition_label_drag_guard_html,
        enhance_transition_readable_exports_html,
        enhance_transition_readable_layout_html,
        enhance_transition_layout_transaction_html,
        enhance_transition_label_inspector_html,
        enhance_transition_layout_interaction_adapter_html,
        enhance_transition_layout_tab_guard_html,
        enhance_transition_semantic_status_ui_html,
        enhance_adaptive_state_focus_html,
        enhance_save_controller_html,
        enhance_save_presentation_html,
    )


def prepare_diagram_app() -> None:
    """Install the compiler and the bounded ordinary-diagram presentation once."""

    install_serial_compilation()
    _install_diagram_diagnostic_localization()
    html = diagram_app.DIAGRAM_HTML
    for enhancer in _presentation_pipeline():
        html = enhancer(html)
    diagram_app.DIAGRAM_HTML = html


def run_diagram_app(input_path: str | Path) -> int:
    """Run the editable app from the compiler-derived diagram snapshot."""

    prepare_diagram_app()
    return diagram_app.run_diagram_app(input_path)

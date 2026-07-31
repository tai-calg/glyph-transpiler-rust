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
from .diagram_fit_stability import enhance_diagram_fit_stability_html
from .diagram_geometry_kernel import enhance_diagram_geometry_kernel_html
from .diagram_label_editor import enhance_diagram_label_editor_html
from .diagram_live_stability import (
    enhance_diagram_live_stability_html,
    install_serial_compilation,
)
from .diagram_locale import enhance_diagram_locale_html
from .diagram_rendered_geometry_adapter import enhance_diagram_rendered_geometry_html
from .diagram_workspace_layout import enhance_workspace_layout_html
from .initial_transition_dependency_bridge import (
    enhance_initial_transition_dependency_bridge_html,
)
from .initial_transition_layout import enhance_initial_transition_html
from .layout_compact_shelf_repair import enhance_layout_compact_shelf_repair_html
from .layout_corridor_fast_repair import enhance_layout_corridor_fast_repair_html
from .layout_corridor_repair import enhance_layout_corridor_repair_html
from .layout_dependency_bridge import enhance_layout_dependency_bridge_html
from .layout_local_repair import enhance_layout_local_repair_html
from .layout_publication_certificate import enhance_layout_publication_certificate_html
from .layout_shelf_repair import enhance_layout_shelf_repair_html
from .layout_shelf_viewport_sync import enhance_layout_shelf_viewport_sync_html
from .state_transition_ir_renderer import enhance_state_transition_ir_html
from .state_viewport_reservation import enhance_state_viewport_reservation_html
from .transition_dense_canvas_dimensions import (
    enhance_transition_dense_canvas_dimensions_html,
)
from .transition_enabling_case_rendering import (
    enhance_transition_enabling_case_rendering_html,
)
from .transition_execution_context_selector import (
    enhance_transition_execution_context_selector_html,
)
from .transition_io_clusters import enhance_transition_io_clusters_html
from .transition_io_collision_solver import enhance_transition_io_collision_solver_html
from .transition_label_drag_guard import enhance_transition_label_drag_guard_html
from .transition_label_layout import enhance_diagram_html
from .transition_label_readability import enhance_transition_label_readability_html
from .transition_layout_interaction_adapter import (
    enhance_transition_layout_interaction_adapter_html,
)
from .transition_layout_tab_guard import enhance_transition_layout_tab_guard_html
from .transition_layout_transaction import enhance_transition_layout_transaction_html
from .transition_layout_transaction_bootstrap import (
    enhance_transition_layout_transaction_bootstrap_html,
)
from .transition_node_layout_guard import enhance_transition_node_layout_guard_html
from .transition_node_position_adapter import (
    enhance_transition_node_position_adapter_html,
)
from .transition_readable_exports import enhance_transition_readable_exports_html
from .transition_readable_layout import enhance_transition_readable_layout_html
from .transition_route_labels import enhance_transition_route_html
from .transition_semantic_role_lines import enhance_transition_semantic_role_lines_html
from .transition_semantic_status_ui import enhance_transition_semantic_status_ui_html
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


def _presentation_pipeline():
    """Return the deterministic inner-to-outer presentation pipeline."""

    return (
        enhance_diagram_geometry_kernel_html,
        enhance_diagram_rendered_geometry_html,
        enhance_diagram_html,
        enhance_transition_layout_transaction_bootstrap_html,
        enhance_uml_transition_html,
        enhance_transition_route_html,
        enhance_initial_transition_html,
        enhance_initial_transition_dependency_bridge_html,
        enhance_state_transition_ir_html,
        enhance_diagram_editor_exports_html,
        enhance_diagram_editor_route_guard_html,
        enhance_diagram_editor_render_guard_html,
        enhance_code_derived_system_html,
        enhance_diagram_live_stability_html,
        enhance_diagram_label_editor_html,
        enhance_workspace_layout_html,
        enhance_state_viewport_reservation_html,
        enhance_diagram_canvas_navigation_html,
        enhance_diagram_canvas_viewport_html,
        enhance_transition_io_clusters_html,
        enhance_transition_io_collision_solver_html,
        enhance_diagram_locale_html,
        enhance_transition_label_readability_html,
        enhance_transition_node_layout_guard_html,
        enhance_transition_label_drag_guard_html,
        enhance_transition_readable_exports_html,
        enhance_transition_readable_layout_html,
        enhance_transition_enabling_case_rendering_html,
        enhance_transition_semantic_role_lines_html,
        enhance_transition_dense_canvas_dimensions_html,
        enhance_transition_layout_transaction_html,
        enhance_transition_layout_interaction_adapter_html,
        enhance_transition_node_position_adapter_html,
        enhance_transition_layout_tab_guard_html,
        enhance_transition_execution_context_selector_html,
        enhance_transition_semantic_status_ui_html,
        enhance_layout_local_repair_html,
        enhance_layout_corridor_repair_html,
        enhance_layout_corridor_fast_repair_html,
        enhance_layout_shelf_repair_html,
        enhance_layout_compact_shelf_repair_html,
        enhance_layout_shelf_viewport_sync_html,
        enhance_diagram_fit_stability_html,
        enhance_layout_dependency_bridge_html,
        enhance_layout_publication_certificate_html,
    )


def prepare_diagram_app() -> None:
    """Install the shared compiler and ordered presentation contracts once."""

    install_serial_compilation()
    _install_diagram_diagnostic_localization()
    html = diagram_app.DIAGRAM_HTML
    for enhancer in _presentation_pipeline():
        html = enhancer(html)
    diagram_app.DIAGRAM_HTML = html


def run_diagram_app(input_path: str | Path) -> int:
    """Run the editable app from StateTransitionIR v4 plus enabling-cases v1."""

    prepare_diagram_app()
    return diagram_app.run_diagram_app(input_path)

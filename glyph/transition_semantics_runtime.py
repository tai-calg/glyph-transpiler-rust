from __future__ import annotations

from .artifacts import CompilationModel
from .state_transition_compiler import (
    STATE_TRANSITION_IR_SCHEMA,
    STATE_TRANSITION_IR_VERSION,
)
from .state_transition_pipeline import enrich_state_transition_ir


def enrich_runtime_io_state_views(
    model: CompilationModel,
    views: dict[str, object],
) -> dict[str, object]:
    """Compatibility entry point; canonical views require no runtime repair."""

    marker = views.get("state_transition_ir", {})
    if (
        marker.get("schema") == STATE_TRANSITION_IR_SCHEMA
        and marker.get("version") == STATE_TRANSITION_IR_VERSION
    ):
        return views
    return enrich_state_transition_ir(model, views)

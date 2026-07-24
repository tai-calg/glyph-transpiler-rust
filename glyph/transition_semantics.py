from __future__ import annotations

from .artifacts import CompilationModel
from .state_transition_compiler import (
    STATE_TRANSITION_IR_SCHEMA,
    STATE_TRANSITION_IR_VERSION,
    build_machine_state_transition_ir,
    enrich_state_transition_ir,
)


def enrich_io_state_views(
    model: CompilationModel,
    views: dict[str, object],
) -> dict[str, object]:
    """Compatibility facade for callers of the former enrichment pass."""

    marker = views.get("state_transition_ir", {})
    if (
        marker.get("schema") == STATE_TRANSITION_IR_SCHEMA
        and marker.get("version") == STATE_TRANSITION_IR_VERSION
    ):
        return views
    return enrich_state_transition_ir(model, views)


__all__ = [
    "STATE_TRANSITION_IR_SCHEMA",
    "STATE_TRANSITION_IR_VERSION",
    "build_machine_state_transition_ir",
    "enrich_io_state_views",
]

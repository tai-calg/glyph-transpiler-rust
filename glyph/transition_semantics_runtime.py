from __future__ import annotations

from .artifacts import CompilationModel
from .state_transition_ir import (
    STATE_TRANSITION_IR_SCHEMA,
    STATE_TRANSITION_IR_VERSION,
    enrich_state_transition_ir,
)


def enrich_runtime_io_state_views(
    model: CompilationModel,
    views: dict[str, object],
) -> dict[str, object]:
    """Compatibility entry point for pre-v2 application integrations.

    StateTransitionIR is now produced by the compiler view builder. No nested
    target repair, failure-edge restoration, or diagnostic reconstruction occurs
    at runtime. Unversioned legacy views are upgraded through the canonical v2
    builder once.
    """

    marker = views.get("state_transition_ir", {})
    if (
        marker.get("schema") == STATE_TRANSITION_IR_SCHEMA
        and marker.get("version") == STATE_TRANSITION_IR_VERSION
    ):
        return views
    return enrich_state_transition_ir(model, views)

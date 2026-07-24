from __future__ import annotations

from copy import deepcopy

from .artifacts import CompilationModel
from .state_transition_block_lowering import lower_analyzed_block_transitions
from .state_transition_compiler import enrich_state_transition_ir as compile_state_transition_ir


def enrich_state_transition_ir(
    model: CompilationModel,
    views: dict[str, object],
) -> dict[str, object]:
    """Compile all machines to StateTransitionIR v2 using explicit lowering paths."""

    original = deepcopy(views)
    result = compile_state_transition_ir(model, views)
    analyzed_by_name = {
        str(machine.get("name", "")): machine
        for machine in original.get("state", {}).get("machines", [])
    }
    state = dict(result.get("state", {}))
    state["machines"] = [
        lower_analyzed_block_transitions(
            model,
            dict(machine),
            dict(analyzed_by_name.get(str(machine.get("name", "")), {})),
        )
        for machine in state.get("machines", [])
    ]
    result["state"] = state
    summary = dict(result.get("summary", {}))
    summary["state_warnings"] = sum(
        1
        for machine in state["machines"]
        for diagnostic in machine.get("diagnostics", [])
        if diagnostic.get("severity") == "warning"
    )
    result["summary"] = summary
    return result

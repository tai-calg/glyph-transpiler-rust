from __future__ import annotations

from copy import deepcopy

from .artifacts import CompilationModel
from .diagnostic_localization import localize_state_views
from .state_transition_block_lowering import lower_analyzed_block_transitions
from .state_transition_compiler import enrich_state_transition_ir as compile_state_transition_ir
from .transition_action_projection import project_machine_transition_actions
from .transition_condition_roles import (
    STATE_TRANSITION_IR_SCHEMA,
    STATE_TRANSITION_IR_VERSION,
    classify_machine_transition_roles,
)


def enrich_state_transition_ir(
    model: CompilationModel,
    views: dict[str, object],
) -> dict[str, object]:
    """Compile machines and classify StateTransitionIR v4 semantic roles."""

    original = deepcopy(views)
    result = compile_state_transition_ir(model, views)
    analyzed_by_name = {
        str(machine.get("name", "")): machine
        for machine in original.get("state", {}).get("machines", [])
    }
    state = dict(result.get("state", {}))
    lowered = [
        lower_analyzed_block_transitions(
            model,
            dict(machine),
            dict(analyzed_by_name.get(str(machine.get("name", "")), {})),
        )
        for machine in state.get("machines", [])
    ]
    projected = [
        project_machine_transition_actions(model, machine) for machine in lowered
    ]
    state["machines"] = [
        classify_machine_transition_roles(model, machine) for machine in projected
    ]
    result["state"] = state
    result["state_transition_ir"] = {
        "schema": STATE_TRANSITION_IR_SCHEMA,
        "version": STATE_TRANSITION_IR_VERSION,
    }
    # This marker describes the public trigger[guard]/Action display contract.
    # StateTransitionIR has its own independently versioned schema marker above.
    result["transition_semantics_version"] = 2
    summary = dict(result.get("summary", {}))
    summary["state_warnings"] = sum(
        1
        for machine in state["machines"]
        for diagnostic in machine.get("diagnostics", [])
        if diagnostic.get("severity") == "warning"
    )
    result["summary"] = summary
    return localize_state_views(result)

from __future__ import annotations

from copy import deepcopy

from .artifacts import CompilationModel
from .nested_transition_repair import repair_nested_transition_targets
from .transition_semantics import enrich_io_state_views


def _diagnosed_state(message: str, state_names: set[str]) -> str | None:
    for state_name in state_names:
        if message.startswith(f"state {state_name} is unreachable"):
            return state_name
    return None


def enrich_runtime_io_state_views(
    model: CompilationModel,
    views: dict[str, object],
) -> dict[str, object]:
    """Enrich transitions and preserve only still-valid static diagnostics."""

    repaired = repair_nested_transition_targets(model, views)
    base = deepcopy(repaired)
    result = enrich_io_state_views(model, repaired)
    base_machines = {
        str(machine.get("name")): machine
        for machine in base.get("state", {}).get("machines", [])
    }
    for machine in result.get("state", {}).get("machines", []):
        name = str(machine.get("name"))
        original = base_machines.get(name, {})
        state_names = {
            str(state.get("name"))
            for state in machine.get("states", [])
        }
        unreachable = set(map(str, machine.get("unreachable_states", [])))
        restored = []
        for diagnostic in original.get("diagnostics", []):
            if diagnostic.get("code") != "unreachable-state":
                continue
            diagnosed = _diagnosed_state(str(diagnostic.get("message", "")), state_names)
            if diagnosed in unreachable:
                restored.append(diagnostic)

        has_explicit_source = any(
            not bool(transition.get("expanded_from_wildcard", False))
            for transition in machine.get("transitions", [])
        )
        non_reachability = [
            diagnostic
            for diagnostic in machine.get("diagnostics", [])
            if diagnostic.get("code") != "unreachable-state"
            and not (
                diagnostic.get("code") == "state-independent-transition"
                and has_explicit_source
            )
        ]
        machine["diagnostics"] = [*non_reachability, *restored]

    summary = dict(result.get("summary", {}))
    summary["state_warnings"] = sum(
        len(machine.get("diagnostics", []))
        for machine in result.get("state", {}).get("machines", [])
    )
    result["summary"] = summary
    return result

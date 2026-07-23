from __future__ import annotations

from copy import deepcopy

from .artifacts import CompilationModel
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
    """Enrich transitions and preserve only still-valid reachability warnings."""

    base = deepcopy(views)
    result = enrich_io_state_views(model, views)
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
        non_reachability = [
            diagnostic
            for diagnostic in machine.get("diagnostics", [])
            if diagnostic.get("code") != "unreachable-state"
        ]
        machine["diagnostics"] = [*non_reachability, *restored]
    return result

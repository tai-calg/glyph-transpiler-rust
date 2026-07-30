from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from .artifacts import CompilationModel
from .compiler import FunctionDecl
from .transition_system_execution_control_flow_v2 import (
    attach_transition_system_execution_actions as _attach_execution_actions,
)


_UNPROVEN_STATE_INPUT_CODE = "STIR_SYSTEM_STATE_INPUT_UNPROVEN"


def _function_declarations(model: CompilationModel) -> dict[str, FunctionDecl]:
    return {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, FunctionDecl)
    }


def _state_specialization_is_proven(
    model: CompilationModel,
    machine_name: str,
    binding: Mapping[str, object],
    functions: Mapping[str, FunctionDecl],
) -> bool:
    """Return whether source-state substitution has explicit System wiring evidence.

    The underlying evaluator only substitutes a source-state value when an entry has
    exactly one parameter of the machine state type.  Type uniqueness alone is not
    semantic evidence that the parameter is the current machine state.  For an
    explicit System context, require the conventional machine-state name at every
    boundary: machine parameter, System input port, System edge, and entry parameter.
    Implicit callers remain unproven and are conservatively blocked.
    """

    machine = next((item for item in model.machines if item.name == machine_name), None)
    if machine is None:
        return False
    entry = str(binding.get("entry") or "")
    declaration = functions.get(entry)
    if declaration is None:
        return False

    state_parameters = [
        parameter
        for parameter in declaration.params
        if parameter.ty == machine.state_param.ty
    ]
    # No substitution occurs when there are zero or multiple state-typed parameters.
    if len(state_parameters) != 1:
        return True

    parameter = state_parameters[0]
    expected_name = machine.state_param.name
    if parameter.name != expected_name:
        return False

    system_name = binding.get("system")
    if not isinstance(system_name, str) or not system_name:
        return False
    system = next((item for item in model.systems if item.name == system_name), None)
    if system is None or system.entry_name != entry:
        return False

    has_input_port = any(
        port.direction == "input" and port.name == expected_name
        for port in system.ports
    )
    has_entry_edge = any(
        edge.source_name == expected_name and edge.target_name == entry
        for edge in system.edges
    )
    return has_input_port and has_entry_edge


def _blocked_binding(binding: Mapping[str, object]) -> dict[str, object]:
    result = deepcopy(dict(binding))
    result["status"] = "unresolved"
    result["action"] = None
    result["action_invocations"] = []
    result["effect_invocations"] = []
    result["state_specialization"] = {
        "status": "unproven",
        "reason": "current-machine-state input is not proven by System wiring",
    }
    cases: list[dict[str, object]] = []
    for original in result.get("action_cases", []):
        if not isinstance(original, Mapping):
            continue
        case = deepcopy(dict(original))
        case["status"] = "unresolved"
        case["action"] = None
        case["action_invocations"] = []
        case["effect_invocations"] = []
        cases.append(case)
    result["action_cases"] = cases
    for key in ("execution_flow", "dataflow"):
        value = result.get(key)
        if isinstance(value, Mapping):
            record = deepcopy(dict(value))
            record["status"] = "unresolved"
            result[key] = record
    return result


def _append_diagnostic_once(
    diagnostics: list[dict[str, object]],
    diagnostic: dict[str, object],
) -> None:
    key = (
        diagnostic.get("code"),
        diagnostic.get("line"),
        diagnostic.get("message"),
    )
    if any(
        (item.get("code"), item.get("line"), item.get("message")) == key
        for item in diagnostics
    ):
        return
    diagnostics.append(diagnostic)


def _recount_analysis(machine: dict[str, object]) -> None:
    bindings = [
        binding
        for transition in machine.get("transitions", [])
        if isinstance(transition, Mapping)
        for binding in transition.get("execution_action_bindings", [])
        if isinstance(binding, Mapping)
    ]
    analysis = dict(machine.get("analysis", {}))
    analysis.update(
        {
            "execution_action_binding_count": len(bindings),
            "execution_action_actionless_count": sum(
                binding.get("action") is None for binding in bindings
            ),
            "execution_action_conditional_count": sum(
                binding.get("status") == "conditional" for binding in bindings
            ),
            "execution_action_unresolved_count": sum(
                binding.get("status") == "unresolved" for binding in bindings
            ),
            "execution_action_multiple_transition_call_count": sum(
                binding.get("status") == "multiple-transition-calls"
                for binding in bindings
            ),
        }
    )
    machine["analysis"] = analysis


def attach_transition_system_execution_actions(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Apply only correctness-critical guards around System execution projection."""

    result = _attach_execution_actions(model, machine_view)
    machine_name = str(result.get("name") or "")
    functions = _function_declarations(model)
    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
    transitions: list[dict[str, object]] = []

    for original in result.get("transitions", []):
        transition = deepcopy(dict(original))

        # A synthesized failure edge represents failure before the machine result is
        # returned.  Caller-side post-transition operations therefore cannot run.
        if transition.get("synthesized_failure"):
            transition["execution_action_bindings"] = []
            transition["execution_contexts"] = []
            transitions.append(transition)
            continue

        source = transition.get("source", {})
        line = int(source.get("line", 1)) if isinstance(source, Mapping) else 1
        bindings: list[dict[str, object]] = []
        for original_binding in transition.get("execution_action_bindings", []):
            if not isinstance(original_binding, Mapping):
                continue
            binding = deepcopy(dict(original_binding))
            if not _state_specialization_is_proven(
                model,
                machine_name,
                binding,
                functions,
            ):
                binding = _blocked_binding(binding)
                _append_diagnostic_once(
                    diagnostics,
                    {
                        "severity": "warning",
                        "code": _UNPROVEN_STATE_INPUT_CODE,
                        "message": (
                            f"system `{binding.get('system')}` entry `{binding.get('entry')}` "
                            "has a state-typed parameter that is not proven to be the current "
                            "machine state by explicit System input wiring"
                        ),
                        "line": line,
                    },
                )
            bindings.append(binding)
        transition["execution_action_bindings"] = bindings
        transition["execution_contexts"] = [deepcopy(item) for item in bindings]
        transitions.append(transition)

    result["transitions"] = transitions
    result["diagnostics"] = diagnostics
    _recount_analysis(result)
    return result


__all__ = ["attach_transition_system_execution_actions"]

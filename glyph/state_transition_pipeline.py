from __future__ import annotations

from copy import deepcopy

from .artifacts import CompilationModel
from .compiler import FieldExpr, ProductDecl
from .diagnostic_localization import localize_state_views
from .state_transition_block_lowering import lower_analyzed_block_transitions
from .state_transition_compiler import enrich_state_transition_ir as compile_state_transition_ir
from .transition_action_projection import project_machine_transition_actions
from .transition_action_target_independence import analyze_action_target_independence
from .transition_condition_roles import (
    STATE_TRANSITION_IR_SCHEMA,
    STATE_TRANSITION_IR_VERSION,
    classify_machine_transition_roles,
)
from .transition_enabling_cases import (
    ENABLING_CASE_VERSION,
    attach_machine_enabling_cases,
)
from .transition_input_provenance import (
    INPUT_PREIMAGE_VERSION,
    expand_machine_transition_inputs,
)


_LEGACY_TRANSITION_FIELDS = (
    "trigger",
    "guards",
    "event",
    "guard",
    "display_label",
    "classification",
    "unclassified_conditions",
)


def _target_state_projection_type(
    model: CompilationModel,
    machine_name: str,
) -> str | None:
    machine = next((item for item in model.machines if item.name == machine_name), None)
    if machine is None or not isinstance(machine.selector, FieldExpr):
        return None
    state_decl = next(
        (
            item
            for item in model.program.declarations
            if isinstance(item, ProductDecl) and item.name == machine.state_param.ty.name
        ),
        None,
    )
    if state_decl is None:
        return None
    field = next(
        (item for item in state_decl.fields if item.name == machine.selector.field),
        None,
    )
    return field.ty.name if field is not None else None


def _attach_enabling_cases_preserving_legacy(
    model: CompilationModel,
    machine: dict[str, object],
) -> dict[str, object]:
    """Add Enabling Cases while keeping the pre-v1 compatibility view unchanged."""

    original_by_id = {
        str(item.get("id") or f"T{index + 1}"): dict(item)
        for index, item in enumerate(machine.get("transitions", []))
    }
    result = attach_machine_enabling_cases(model, machine)
    transitions: list[dict[str, object]] = []
    for index, item in enumerate(result.get("transitions", [])):
        transition = dict(item)
        transition_id = str(transition.get("id") or f"T{index + 1}")
        legacy = original_by_id.get(transition_id, {})
        for field in _LEGACY_TRANSITION_FIELDS:
            if field in legacy:
                transition[field] = deepcopy(legacy[field])
            else:
                transition.pop(field, None)
        transitions.append(transition)
    result["transitions"] = transitions
    return result


def _attach_action_target_independence(
    model: CompilationModel,
    machine: dict[str, object],
) -> dict[str, object]:
    result = dict(machine)
    action_projection = result.get("action_projection")
    action_type = (
        str(action_projection.get("type") or "")
        if isinstance(action_projection, dict)
        else ""
    )
    state_type = _target_state_projection_type(model, str(result.get("name") or ""))
    independence, generated = analyze_action_target_independence(
        result.get("transitions", []),
        action_type=action_type or None,
        state_type=state_type,
    )

    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
    seen = {
        (item.get("code"), item.get("line"), item.get("message"))
        for item in diagnostics
    }
    for item in generated:
        key = (item.get("code"), item.get("line"), item.get("message"))
        if key not in seen:
            diagnostics.append(item)
            seen.add(key)

    analysis = dict(result.get("analysis", {}))
    analysis["action_target_independence"] = independence
    result["analysis"] = analysis
    result["diagnostics"] = diagnostics
    return result


def enrich_state_transition_ir(
    model: CompilationModel,
    views: dict[str, object],
) -> dict[str, object]:
    """Compile machines and classify StateTransitionIR semantic roles."""

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
    classified = [
        classify_machine_transition_roles(model, machine) for machine in projected
    ]
    expanded = [
        expand_machine_transition_inputs(model, machine) for machine in classified
    ]
    cased = [
        _attach_enabling_cases_preserving_legacy(model, machine)
        for machine in expanded
    ]
    state["machines"] = [
        _attach_action_target_independence(model, machine) for machine in cased
    ]
    result["state"] = state
    result["state_transition_ir"] = {
        "schema": STATE_TRANSITION_IR_SCHEMA,
        "version": STATE_TRANSITION_IR_VERSION,
    }
    # The public Input [Guard] ➞ Action shape remains contract version 2.
    # Input-preimage expansion, Enabling Cases, and Action/Target independence
    # are independently versioned backward-compatible semantic extensions.
    result["transition_semantics_version"] = 2
    result["transition_input_preimage_version"] = INPUT_PREIMAGE_VERSION
    result["transition_enabling_case_version"] = ENABLING_CASE_VERSION
    result["transition_action_target_independence_version"] = 1
    summary = dict(result.get("summary", {}))
    summary["state_warnings"] = sum(
        1
        for machine in state["machines"]
        for diagnostic in machine.get("diagnostics", [])
        if diagnostic.get("severity") == "warning"
    )
    result["summary"] = summary
    return localize_state_views(result)

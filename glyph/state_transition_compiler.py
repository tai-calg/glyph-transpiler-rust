from __future__ import annotations

from copy import deepcopy

from ._transition_branch_semantics import (
    build_machine_branch_context,
    planned_source_branches,
)
from .artifacts import CompilationModel
from .compiler import AliasDecl, ExternDecl
from .state_transition_ir import (
    STATE_TRANSITION_IR_SCHEMA,
    STATE_TRANSITION_IR_VERSION,
    _actions_in_expr,
    _deduplicate,
    _display_label,
    _reachable,
    _selector_sources,
    _split_condition,
)


def build_machine_state_transition_ir(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    result = deepcopy(machine_view)
    context = build_machine_branch_context(model, str(result.get("name") or ""))
    if context is None:
        return result

    externs = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, ExternDecl)
    }
    aliases = {
        item.name: item.target
        for item in model.program.declarations
        if isinstance(item, AliasDecl)
    }
    machine = context.machine
    state_names = [str(item.get("name", "")) for item in result.get("states", [])]
    unreachable_lines = frozenset(map(int, result.get("unreachable_branches", [])))
    root_locals = {parameter.name: parameter.ty for parameter in machine.params}
    transitions: list[dict[str, object]] = []

    for planned in planned_source_branches(
        context,
        state_names,
        unreachable_lines=unreachable_lines,
    ):
        branch = planned.branch
        source_state = planned.source_state
        target_state = planned.target_state
        explicit_sources = _selector_sources(
            branch.condition,
            state_param=machine.state_param.name,
            selector_field=machine.selector.field,
            variants=set(context.selector_variants),
        )
        condition_raw = (
            "otherwise"
            if branch.condition is None
            else __import__("glyph.execution_ir", fromlist=["render_expr"]).render_expr(
                branch.condition
            )
        )
        actions = _actions_in_expr(
            planned.value,
            functions=context.functions,
            externs=externs,
            aliases=aliases,
        )
        action_text = "; ".join(action.call for action in actions) or None
        event, guard = _split_condition(
            branch.condition,
            state_param=machine.state_param.name,
            selector_field=machine.selector.field,
            source_state=source_state,
            locals_=root_locals,
            products=context.products,
            sums=context.sums,
        )
        outcome = (
            "failure"
            if target_state == str(result.get("failure_state", machine.failure))
            else "success"
            if target_state == str(result.get("success_state", machine.success))
            else "normal"
        )
        normal = {
            "source_state": source_state,
            "target_state": target_state,
            "condition": condition_raw,
            "condition_raw": condition_raw,
            "event": event,
            "guard": guard,
            "action": action_text,
            "failure_type": None,
            "outcome": outcome,
            "display_label": _display_label(event, guard, action_text),
            "source": {"line": branch.line, "column": 1},
            "expanded_from_wildcard": not bool(explicit_sources),
            "synthesized_failure": False,
        }
        transitions.append(normal)

        if outcome == "failure":
            continue
        failure_state = str(result.get("failure_state", machine.failure))
        if failure_state not in state_names:
            continue
        for action in actions:
            if action.failure_type is None:
                continue
            transitions.append(
                {
                    **normal,
                    "target_state": failure_state,
                    "action": action.call,
                    "failure_type": action.failure_type,
                    "outcome": "failure",
                    "display_label": _display_label(
                        event,
                        guard,
                        action.call,
                        action.failure_type,
                    ),
                    "synthesized_failure": True,
                }
            )

    transitions = _deduplicate(transitions)
    initial = str(result.get("initial_state", ""))
    reachable = _reachable(initial, transitions)
    unreachable_states = [name for name in state_names if name not in reachable]
    for index, transition in enumerate(transitions, start=1):
        transition["id"] = f"T{index}"
        transition["source_reachable"] = transition["source_state"] in reachable

    states = []
    for state in result.get("states", []):
        item = dict(state)
        item["reachable"] = str(item.get("name", "")) in reachable
        states.append(item)

    diagnostics = [
        dict(item)
        for item in result.get("diagnostics", [])
        if item.get("code")
        not in {"unreachable-state", "state-independent-transition", "no-static-transitions"}
    ]
    state_sources = {
        str(item.get("name", "")): int(item.get("source", {}).get("line", 1))
        for item in states
    }
    for state_name in unreachable_states:
        diagnostics.append(
            {
                "severity": "warning",
                "code": "unreachable-state",
                "message": f"state {state_name} is unreachable from initial state {initial}",
                "line": state_sources.get(state_name, 1),
            }
        )
    if transitions and all(item.get("expanded_from_wildcard") for item in transitions):
        diagnostics.append(
            {
                "severity": "warning",
                "code": "state-independent-transition",
                "message": (
                    "next-state logic does not constrain any transition by the "
                    f"selector {result.get('selector', machine.selector.field)}; "
                    "every active branch applies to every state"
                ),
                "line": getattr(machine, "next_line", getattr(machine, "line", 1)),
            }
        )
    if not transitions:
        diagnostics.append(
            {
                "severity": "warning",
                "code": "no-static-transitions",
                "message": "no state transition could be derived statically",
                "line": getattr(machine, "next_line", getattr(machine, "line", 1)),
            }
        )

    analysis = dict(result.get("analysis", {}))
    analysis.update(
        {
            "normalized_transition_count": len(transitions),
            "reachable_state_count": len(reachable),
            "failure_transition_count": sum(
                1 for item in transitions if item.get("outcome") == "failure"
            ),
            "synthesized_failure_transition_count": sum(
                1 for item in transitions if item.get("synthesized_failure")
            ),
            "source_specialized_branch_count": len(transitions),
            "transition_ir_schema": STATE_TRANSITION_IR_SCHEMA,
            "transition_ir_version": STATE_TRANSITION_IR_VERSION,
        }
    )
    result.update(
        {
            "states": states,
            "transitions": transitions,
            "unreachable_states": unreachable_states,
            "diagnostics": diagnostics,
            "analysis": analysis,
            "transition_ir": {
                "schema": STATE_TRANSITION_IR_SCHEMA,
                "version": STATE_TRANSITION_IR_VERSION,
            },
        }
    )
    return result


def enrich_state_transition_ir(
    model: CompilationModel,
    views: dict[str, object],
) -> dict[str, object]:
    result = deepcopy(views)
    state = dict(result.get("state", {}))
    state["machines"] = [
        build_machine_state_transition_ir(model, dict(machine))
        for machine in state.get("machines", [])
    ]
    result["state"] = state
    result["state_transition_ir"] = {
        "schema": STATE_TRANSITION_IR_SCHEMA,
        "version": STATE_TRANSITION_IR_VERSION,
    }
    result["transition_semantics_version"] = 1
    summary = dict(result.get("summary", {}))
    summary["state_warnings"] = sum(
        1
        for machine in state["machines"]
        for diagnostic in machine.get("diagnostics", [])
        if diagnostic.get("severity") == "warning"
    )
    result["summary"] = summary
    return result

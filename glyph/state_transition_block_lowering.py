from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from .artifacts import CompilationModel
from .compiler import AliasDecl, ExternDecl, FieldExpr, FunctionDecl, ProductDecl, SumDecl, TypeRef
from .execution_ir import render_expr
from .state_transition_ir import (
    _actions_in_expr,
    _deduplicate,
    _display_label,
    _failure_type,
    _reachable,
    _split_condition,
)


def _guard_clause_by_line(
    functions: Mapping[str, FunctionDecl],
    line: int,
    rendered_condition: str,
):
    matches = []
    for declaration in functions.values():
        for clause in declaration.guards:
            condition = "otherwise" if clause.condition is None else render_expr(clause.condition)
            if clause.line == line and condition == rendered_condition:
                matches.append(clause)
    return matches[0] if len(matches) == 1 else None


def lower_analyzed_block_transitions(
    model: CompilationModel,
    canonical_machine: dict[str, object],
    analyzed_machine: dict[str, object],
) -> dict[str, object]:
    """Use compiler-normalized transitions when function-block lowering hid guards.

    Immutable `:=` blocks are lowered into generated continuation functions before
    the normal AST pass. `analyze_machine` already resolves those continuations and
    emits concrete, wildcard-free transitions. This alternate compiler lowering
    attaches StateTransitionIR v2 fields to that validated result; it never edits a
    rendered graph and never guesses a missing source or target.
    """

    if canonical_machine.get("transitions") or not analyzed_machine.get("transitions"):
        return canonical_machine

    result = deepcopy(canonical_machine)
    machine = next(
        (item for item in model.machines if item.name == result.get("name")),
        None,
    )
    if machine is None or not isinstance(machine.selector, FieldExpr):
        return result

    products = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, ProductDecl)
    }
    sums = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, SumDecl)
    }
    functions = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, FunctionDecl)
    }
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
    locals_: dict[str, TypeRef] = {
        parameter.name: parameter.ty for parameter in machine.params
    }
    state_names = [str(item.get("name", "")) for item in result.get("states", [])]
    transitions: list[dict[str, object]] = []

    for base in analyzed_machine.get("transitions", []):
        source_state = str(base.get("source_state", ""))
        target_state = str(base.get("target_state", ""))
        if source_state not in state_names or target_state not in state_names:
            continue
        raw = str(base.get("condition", ""))
        line = int(base.get("source", {}).get("line", 1))
        clause = _guard_clause_by_line(functions, line, raw)
        if clause is None:
            event = None
            guard = None if raw in {"", "otherwise", "next"} else raw
            actions = ()
        else:
            event, guard = _split_condition(
                clause.condition,
                state_param=machine.state_param.name,
                selector_field=machine.selector.field,
                source_state=source_state,
                locals_=locals_,
                products=products,
                sums=sums,
            )
            actions = _actions_in_expr(
                clause.value,
                functions=functions,
                externs=externs,
                aliases=aliases,
            )
        action_text = "; ".join(action.call for action in actions) or None
        outcome = (
            "failure"
            if target_state == str(result.get("failure_state", machine.failure))
            else "success"
            if target_state == str(result.get("success_state", machine.success))
            else "normal"
        )
        normal = {
            **dict(base),
            "condition_raw": raw,
            "event": event,
            "guard": guard,
            "action": action_text,
            "failure_type": None,
            "outcome": outcome,
            "display_label": _display_label(event, guard, action_text),
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
                        event, guard, action.call, action.failure_type
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
        for item in analyzed_machine.get("diagnostics", [])
        if item.get("code") != "unreachable-state"
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

    analysis = dict(analyzed_machine.get("analysis", {}))
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
            "transition_ir_schema": "glyph.state-transition-ir",
            "transition_ir_version": 2,
            "lowering_path": "compiler-normalized-function-block",
        }
    )
    result.update(
        {
            "states": states,
            "transitions": transitions,
            "unreachable_states": unreachable_states,
            "unreachable_branches": list(analyzed_machine.get("unreachable_branches", [])),
            "diagnostics": diagnostics,
            "analysis": analysis,
            "transition_ir": {
                "schema": "glyph.state-transition-ir",
                "version": 2,
            },
        }
    )
    return result

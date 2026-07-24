from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from .artifacts import CompilationModel
from .compiler import FunctionDecl
from .execution_ir import render_expr
from .host_invocation_ir import (
    HOST_INVOCATION_IR_SCHEMA,
    HOST_INVOCATION_IR_VERSION,
    HostInvocationPlan,
    resolve_invocations_in_expr,
)
from .state_transition_ir import _display_label


def _expression_by_source(
    functions: Mapping[str, FunctionDecl],
    line: int,
    rendered_condition: str,
):
    guard_candidates = []
    expression_candidates = []
    for declaration in functions.values():
        if declaration.expression is not None and declaration.line == line:
            expression_candidates.append((declaration, declaration.expression))
        for clause in declaration.guards:
            if clause.line != line:
                continue
            condition = "otherwise" if clause.condition is None else render_expr(clause.condition)
            guard_candidates.append((declaration, clause.value, condition))

    exact = [
        (declaration, expression)
        for declaration, expression, condition in guard_candidates
        if condition == rendered_condition
    ]
    if len(exact) == 1:
        return exact[0]
    if len(guard_candidates) == 1:
        declaration, expression, _ = guard_candidates[0]
        return declaration, expression
    if len(expression_candidates) == 1:
        return expression_candidates[0]
    return None


def _select_failure_invocation(transition, invocations):
    failure_type = transition.get("failure_type")
    action = transition.get("action")
    exact = [
        invocation
        for invocation in invocations
        if invocation.failure_type == failure_type and invocation.call == action
    ]
    if len(exact) == 1:
        return exact
    typed = [
        invocation for invocation in invocations if invocation.failure_type == failure_type
    ]
    return typed if len(typed) == 1 else []


def link_host_invocations(
    model: CompilationModel,
    views: dict[str, object],
) -> dict[str, object]:
    """Attach HostInvocationIR call-site IDs to compiler-produced transitions."""

    result = deepcopy(views)
    plan = HostInvocationPlan.from_model(model)
    functions = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, FunctionDecl)
    }
    externs = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if declaration.__class__.__name__ == "ExternDecl"
    }

    state = dict(result.get("state", {}))
    machines = []
    unresolved_total = 0
    linked_total = 0
    for machine in state.get("machines", []):
        machine_item = deepcopy(machine)
        transitions = []
        for transition in machine_item.get("transitions", []):
            item = dict(transition)
            action = str(item.get("action") or "")
            if not action:
                item["action_invocation_ids"] = []
                transitions.append(item)
                continue

            source = item.get("source", {})
            line = int(source.get("line", 1)) if isinstance(source, dict) else 1
            raw = str(item.get("condition_raw", item.get("condition", "")))
            located = _expression_by_source(functions, line, raw)
            resolved = ()
            if located is not None:
                declaration, expression = located
                resolved = resolve_invocations_in_expr(
                    expression,
                    caller=declaration.name,
                    source_line=line,
                    functions=functions,
                    externs=externs,
                    plan=plan,
                )

            selected = (
                _select_failure_invocation(item, resolved)
                if item.get("synthesized_failure")
                else list(resolved)
            )
            item["action_invocation_ids"] = [
                invocation.invocation_id for invocation in selected
            ]
            if selected:
                linked_total += len(selected)
                canonical_action = "; ".join(invocation.call for invocation in selected)
                item["action"] = canonical_action
                item["display_label"] = _display_label(
                    item.get("event"),
                    item.get("guard"),
                    canonical_action,
                    item.get("failure_type"),
                )
            else:
                unresolved_total += 1
            transitions.append(item)

        analysis = dict(machine_item.get("analysis", {}))
        analysis.update(
            {
                "host_invocation_link_count": linked_total,
                "unresolved_host_invocation_count": unresolved_total,
                "host_invocation_ir_schema": HOST_INVOCATION_IR_SCHEMA,
                "host_invocation_ir_version": HOST_INVOCATION_IR_VERSION,
            }
        )
        machine_item["analysis"] = analysis
        machine_item["transitions"] = transitions
        machines.append(machine_item)

    state["machines"] = machines
    result["state"] = state
    result["host_invocation_ir"] = plan.to_dict()
    return result

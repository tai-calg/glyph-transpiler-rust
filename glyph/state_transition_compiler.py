from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping

from .artifacts import CompilationModel
from .compiler import (
    AliasDecl,
    BinaryExpr,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    NameExpr,
    ProductDecl,
    SumDecl,
    TryExpr,
    TypeRef,
    UnaryExpr,
)
from .execution_ir import render_expr
from .state_transition_ir import (
    STATE_TRANSITION_IR_SCHEMA,
    STATE_TRANSITION_IR_VERSION,
    _actions_in_expr,
    _deduplicate,
    _direct_target,
    _display_label,
    _reachable,
    _selector_sources,
    _split_condition,
)


@dataclass(frozen=True)
class _Branch:
    condition: Expr | None
    value: Expr
    target: str
    line: int


def _substitute(expr: Expr, bindings: Mapping[str, Expr]) -> Expr:
    if isinstance(expr, NameExpr):
        return bindings.get(expr.name, expr)
    if isinstance(expr, UnaryExpr):
        return UnaryExpr(expr.op, _substitute(expr.expr, bindings))
    if isinstance(expr, TryExpr):
        return TryExpr(_substitute(expr.expr, bindings))
    if isinstance(expr, BinaryExpr):
        return BinaryExpr(
            expr.op,
            _substitute(expr.left, bindings),
            _substitute(expr.right, bindings),
        )
    if isinstance(expr, FieldExpr):
        return FieldExpr(_substitute(expr.base, bindings), expr.field)
    if isinstance(expr, CallExpr):
        return CallExpr(
            _substitute(expr.callee, bindings),
            tuple(_substitute(argument, bindings) for argument in expr.args),
        )
    return expr


def _unwrap_call(expr: Expr) -> CallExpr | None:
    value = expr
    if isinstance(value, TryExpr):
        return _unwrap_call(value.expr)
    if (
        isinstance(value, CallExpr)
        and isinstance(value.callee, NameExpr)
        and value.callee.name == "Ok"
        and len(value.args) == 1
    ):
        return _unwrap_call(value.args[0])
    return value if isinstance(value, CallExpr) else None


def _combine(left: Expr | None, right: Expr | None) -> Expr | None:
    if left is None:
        return right
    if right is None:
        return left
    return BinaryExpr("&", left, right)


def _call_bindings(declaration: FunctionDecl, call: CallExpr) -> dict[str, Expr] | None:
    if len(declaration.params) != len(call.args):
        return None
    return {
        parameter.name: argument
        for parameter, argument in zip(declaration.params, call.args, strict=True)
    }


def _inline_unguarded(
    expr: Expr,
    functions: Mapping[str, FunctionDecl],
    visited: set[str] | None = None,
) -> Expr:
    """Inline pure single-expression helpers while preserving actual arguments."""

    visited = set() if visited is None else set(visited)
    if isinstance(expr, UnaryExpr):
        return UnaryExpr(expr.op, _inline_unguarded(expr.expr, functions, visited))
    if isinstance(expr, TryExpr):
        return TryExpr(_inline_unguarded(expr.expr, functions, visited))
    if isinstance(expr, BinaryExpr):
        return BinaryExpr(
            expr.op,
            _inline_unguarded(expr.left, functions, visited),
            _inline_unguarded(expr.right, functions, visited),
        )
    if isinstance(expr, FieldExpr):
        return FieldExpr(_inline_unguarded(expr.base, functions, visited), expr.field)
    if not isinstance(expr, CallExpr):
        return expr

    callee = _inline_unguarded(expr.callee, functions, visited)
    args = tuple(_inline_unguarded(argument, functions, visited) for argument in expr.args)
    call = CallExpr(callee, args)
    if not isinstance(callee, NameExpr):
        return call
    declaration = functions.get(callee.name)
    if (
        declaration is None
        or declaration.guards
        or declaration.expression is None
        or declaration.name in visited
    ):
        return call
    bindings = _call_bindings(declaration, call)
    if bindings is None:
        return call
    body = _substitute(declaration.expression, bindings)
    return _inline_unguarded(body, functions, {*visited, declaration.name})


def _trace_function(
    name: str,
    *,
    functions: Mapping[str, FunctionDecl],
    state_decl: ProductDecl,
    selector_index: int,
    variants: set[str],
    root_state_param: str,
    bindings: Mapping[str, Expr],
    inherited_condition: Expr | None,
    visited: tuple[str, ...],
) -> list[_Branch]:
    if name in visited:
        return []
    declaration = functions.get(name)
    if declaration is None:
        return []
    next_visited = (*visited, name)
    branches: list[_Branch] = []

    def trace_value(value: Expr, condition: Expr | None, line: int) -> None:
        substituted = _substitute(value, bindings)
        inlined = _inline_unguarded(substituted, functions)
        target = _direct_target(
            inlined,
            state_decl=state_decl,
            selector_index=selector_index,
            variants=variants,
            state_param=root_state_param,
        )
        if target is not None:
            branches.append(_Branch(condition, inlined, target, line))
            return

        call = _unwrap_call(substituted)
        if call is None or not isinstance(call.callee, NameExpr):
            return
        nested = functions.get(call.callee.name)
        if nested is None or not nested.guards:
            return
        nested_bindings = _call_bindings(nested, call)
        if nested_bindings is None:
            return
        branches.extend(
            _trace_function(
                nested.name,
                functions=functions,
                state_decl=state_decl,
                selector_index=selector_index,
                variants=variants,
                root_state_param=root_state_param,
                bindings=nested_bindings,
                inherited_condition=condition,
                visited=next_visited,
            )
        )

    if declaration.guards:
        for clause in declaration.guards:
            condition = _combine(
                inherited_condition,
                None if clause.condition is None else _substitute(clause.condition, bindings),
            )
            trace_value(clause.value, condition, clause.line)
        return branches

    if declaration.expression is not None:
        trace_value(declaration.expression, inherited_condition, declaration.line)
    return branches


def _root_branches(
    root: str,
    *,
    functions: Mapping[str, FunctionDecl],
    state_decl: ProductDecl,
    selector_index: int,
    variants: set[str],
    root_state_param: str,
) -> tuple[_Branch, ...]:
    declaration = functions.get(root)
    if declaration is None:
        return ()
    identity = {parameter.name: NameExpr(parameter.name) for parameter in declaration.params}
    return tuple(
        _trace_function(
            root,
            functions=functions,
            state_decl=state_decl,
            selector_index=selector_index,
            variants=variants,
            root_state_param=root_state_param,
            bindings=identity,
            inherited_condition=None,
            visited=(),
        )
    )


def build_machine_state_transition_ir(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    result = deepcopy(machine_view)
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
    state_decl = products.get(machine.state_param.ty.name)
    if state_decl is None:
        return result
    selector_index = next(
        (index for index, field in enumerate(state_decl.fields) if field.name == machine.selector.field),
        None,
    )
    if selector_index is None:
        return result
    selector_sum = sums.get(state_decl.fields[selector_index].ty.name)
    if selector_sum is None:
        return result
    variants = {item.name for item in selector_sum.variants}
    next_call = machine.next_expr if isinstance(machine.next_expr, CallExpr) else None
    next_name = (
        next_call.callee.name
        if next_call is not None and isinstance(next_call.callee, NameExpr)
        else None
    )
    if next_name is None:
        return result

    unreachable_lines = set(map(int, result.get("unreachable_branches", [])))
    state_names = [str(item.get("name", "")) for item in result.get("states", [])]
    root_locals = {parameter.name: parameter.ty for parameter in machine.params}
    transitions: list[dict[str, object]] = []

    for branch in _root_branches(
        next_name,
        functions=functions,
        state_decl=state_decl,
        selector_index=selector_index,
        variants=variants,
        root_state_param=machine.state_param.name,
    ):
        if branch.line in unreachable_lines:
            continue
        explicit_sources = _selector_sources(
            branch.condition,
            state_param=machine.state_param.name,
            selector_field=machine.selector.field,
            variants=variants,
        )
        source_names = sorted(explicit_sources) if explicit_sources else state_names
        condition_raw = "otherwise" if branch.condition is None else render_expr(branch.condition)
        actions = _actions_in_expr(
            branch.value,
            functions=functions,
            externs=externs,
            aliases=aliases,
        )
        action_text = "; ".join(action.call for action in actions) or None

        for source_state in source_names:
            target_state = source_state if branch.target == "__same__" else branch.target
            if source_state not in state_names or target_state not in state_names:
                continue
            event, guard = _split_condition(
                branch.condition,
                state_param=machine.state_param.name,
                selector_field=machine.selector.field,
                source_state=source_state,
                locals_=root_locals,
                products=products,
                sums=sums,
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

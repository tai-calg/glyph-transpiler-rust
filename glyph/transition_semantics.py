from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

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


@dataclass(frozen=True)
class _Action:
    call: str
    error_type: str | None


@dataclass(frozen=True)
class _Clause:
    condition: Expr | None
    value: Expr
    rendered_condition: str


def _walk_expr(expr: Expr) -> Iterable[Expr]:
    yield expr
    if isinstance(expr, UnaryExpr):
        yield from _walk_expr(expr.expr)
    elif isinstance(expr, TryExpr):
        yield from _walk_expr(expr.expr)
    elif isinstance(expr, BinaryExpr):
        yield from _walk_expr(expr.left)
        yield from _walk_expr(expr.right)
    elif isinstance(expr, FieldExpr):
        yield from _walk_expr(expr.base)
    elif isinstance(expr, CallExpr):
        yield from _walk_expr(expr.callee)
        for argument in expr.args:
            yield from _walk_expr(argument)


def _render_type(ty: TypeRef) -> str:
    if not ty.args:
        return ty.name
    return f"{ty.name}<{','.join(_render_type(argument) for argument in ty.args)}>"


def _resolve_alias(ty: TypeRef, aliases: Mapping[str, TypeRef]) -> TypeRef:
    current = ty
    seen: set[str] = set()
    while not current.args and current.name in aliases and current.name not in seen:
        seen.add(current.name)
        current = aliases[current.name]
    return current


def _error_type(ty: TypeRef, aliases: Mapping[str, TypeRef]) -> str | None:
    resolved = _resolve_alias(ty, aliases)
    if resolved.name == "R" and len(resolved.args) == 2:
        return _render_type(resolved.args[1])
    return None


def _flatten_and(expr: Expr) -> list[Expr]:
    if isinstance(expr, BinaryExpr) and expr.op == "&":
        return [*_flatten_and(expr.left), *_flatten_and(expr.right)]
    return [expr]


def _join_guard(parts: Sequence[Expr]) -> str | None:
    if not parts:
        return None
    return "&".join(render_expr(part) for part in parts)


def _operand_type(
    expr: Expr,
    locals_: Mapping[str, TypeRef],
    products: Mapping[str, ProductDecl],
) -> TypeRef | None:
    if isinstance(expr, NameExpr):
        return locals_.get(expr.name)
    if isinstance(expr, FieldExpr) and isinstance(expr.base, NameExpr):
        base_type = locals_.get(expr.base.name)
        if base_type is None:
            return None
        product = products.get(base_type.name)
        if product is None:
            return None
        field = next((item for item in product.fields if item.name == expr.field), None)
        return None if field is None else field.ty
    return None


def _variant_name(expr: Expr) -> str | None:
    if isinstance(expr, NameExpr):
        return expr.name
    if isinstance(expr, CallExpr) and isinstance(expr.callee, NameExpr):
        return expr.callee.name
    return None


def _selector_predicate(
    expr: Expr,
    state_param: str,
    selector_field: str,
    source_state: str,
) -> bool:
    if not isinstance(expr, BinaryExpr) or expr.op != "==":
        return False
    for left, right in ((expr.left, expr.right), (expr.right, expr.left)):
        if (
            isinstance(left, FieldExpr)
            and isinstance(left.base, NameExpr)
            and left.base.name == state_param
            and left.field == selector_field
            and isinstance(right, NameExpr)
            and right.name == source_state
        ):
            return True
    return False


def _event_variant(
    expr: Expr,
    locals_: Mapping[str, TypeRef],
    products: Mapping[str, ProductDecl],
    sums: Mapping[str, SumDecl],
    state_param: str,
) -> str | None:
    if not isinstance(expr, BinaryExpr) or expr.op != "==":
        return None
    for subject, pattern in ((expr.left, expr.right), (expr.right, expr.left)):
        if isinstance(subject, FieldExpr) and isinstance(subject.base, NameExpr):
            if subject.base.name == state_param:
                continue
        elif isinstance(subject, NameExpr):
            if subject.name == state_param:
                continue
        else:
            continue
        type_ref = _operand_type(subject, locals_, products)
        variant = _variant_name(pattern)
        if type_ref is None or variant is None:
            continue
        sum_decl = sums.get(type_ref.name)
        if sum_decl is None:
            continue
        if variant in {item.name for item in sum_decl.variants}:
            return variant
    return None


def _split_condition(
    condition: Expr | None,
    *,
    state_param: str,
    selector_field: str,
    source_state: str,
    locals_: Mapping[str, TypeRef],
    products: Mapping[str, ProductDecl],
    sums: Mapping[str, SumDecl],
) -> tuple[str | None, str | None]:
    if condition is None:
        return None, None
    remaining: list[Expr] = []
    events: list[str] = []
    for part in _flatten_and(condition):
        if _selector_predicate(part, state_param, selector_field, source_state):
            continue
        event = _event_variant(part, locals_, products, sums, state_param)
        if event is not None:
            events.append(event)
            continue
        remaining.append(part)
    # Multiple independent event predicates are ambiguous. Keep the whole
    # condition as a guard rather than inventing event ordering.
    if len(events) > 1:
        return None, _join_guard(_flatten_and(condition))
    return (events[0] if events else None), _join_guard(remaining)


def _called_function_names(expr: Expr, functions: Mapping[str, FunctionDecl]) -> tuple[str, ...]:
    names: list[str] = []
    for item in _walk_expr(expr):
        if (
            isinstance(item, CallExpr)
            and isinstance(item.callee, NameExpr)
            and item.callee.name in functions
            and item.callee.name not in names
        ):
            names.append(item.callee.name)
    return tuple(names)


def _function_closure(root: str, functions: Mapping[str, FunctionDecl]) -> tuple[str, ...]:
    ordered: list[str] = []
    pending = [root]
    seen: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen or name not in functions:
            continue
        seen.add(name)
        ordered.append(name)
        declaration = functions[name]
        roots: list[Expr] = []
        if declaration.expression is not None:
            roots.append(declaration.expression)
        for clause in declaration.guards:
            roots.append(clause.value)
        for root_expr in roots:
            pending.extend(reversed(_called_function_names(root_expr, functions)))
    return tuple(ordered)


def _actions_in_expr(
    expr: Expr,
    functions: Mapping[str, FunctionDecl],
    externs: Mapping[str, ExternDecl],
    aliases: Mapping[str, TypeRef],
    visited: set[str] | None = None,
) -> tuple[_Action, ...]:
    visited = set() if visited is None else set(visited)
    actions: list[_Action] = []
    for item in _walk_expr(expr):
        if not isinstance(item, CallExpr) or not isinstance(item.callee, NameExpr):
            continue
        name = item.callee.name
        external = externs.get(name)
        if external is not None:
            call = f"{name}({','.join(render_expr(argument) for argument in item.args)})"
            action = _Action(call, _error_type(external.return_type, aliases))
            if action not in actions:
                actions.append(action)
            continue
        nested = functions.get(name)
        if nested is None or name in visited or nested.guards:
            continue
        visited.add(name)
        if nested.expression is not None:
            for action in _actions_in_expr(
                nested.expression,
                functions,
                externs,
                aliases,
                visited,
            ):
                if action not in actions:
                    actions.append(action)
    return tuple(actions)


def _clauses(closure: Sequence[str], functions: Mapping[str, FunctionDecl]) -> tuple[_Clause, ...]:
    result: list[_Clause] = []
    for name in closure:
        declaration = functions[name]
        for clause in declaration.guards:
            result.append(
                _Clause(
                    clause.condition,
                    clause.value,
                    "otherwise" if clause.condition is None else render_expr(clause.condition),
                )
            )
    return tuple(result)


def _matching_clause(
    raw_condition: str,
    source_state: str,
    clauses: Sequence[_Clause],
    state_param: str,
    selector_field: str,
) -> _Clause | None:
    candidates = [item for item in clauses if item.rendered_condition == raw_condition]
    if not candidates:
        return None
    for candidate in candidates:
        if candidate.condition is None:
            continue
        if any(
            _selector_predicate(part, state_param, selector_field, source_state)
            for part in _flatten_and(candidate.condition)
        ):
            return candidate
    return candidates[0]


def _display_label(event: str | None, guard: str | None, action: str | None) -> str:
    label = event or ""
    if guard:
        label += f" [{guard}]" if label else f"[{guard}]"
    if action:
        label += f" / {action}" if label else f"/ {action}"
    return label


def _reachable(initial: str, transitions: Sequence[dict[str, object]]) -> set[str]:
    reachable = {initial}
    changed = True
    while changed:
        changed = False
        for transition in transitions:
            source = str(transition["source_state"])
            target = str(transition["target_state"])
            if source in reachable and target not in reachable:
                reachable.add(target)
                changed = True
    return reachable


def _enrich_machine(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    machine = next(
        (item for item in model.machines if item.name == machine_view.get("name")),
        None,
    )
    if machine is None or not isinstance(machine.selector, FieldExpr):
        return machine_view

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
    next_name = (
        machine.next_expr.callee.name
        if isinstance(machine.next_expr, CallExpr)
        and isinstance(machine.next_expr.callee, NameExpr)
        else None
    )
    if next_name is None:
        return machine_view

    closure = _function_closure(next_name, functions)
    clauses = _clauses(closure, functions)
    locals_ = {parameter.name: parameter.ty for parameter in machine.params}
    enriched: list[dict[str, object]] = []
    synthesized: list[dict[str, object]] = []
    seen_failures: set[tuple[str, str, str, str]] = set()

    for original in machine_view.get("transitions", []):
        transition = dict(original)
        raw_condition = str(transition.get("condition", ""))
        source_state = str(transition.get("source_state", ""))
        target_state = str(transition.get("target_state", ""))
        clause = _matching_clause(
            raw_condition,
            source_state,
            clauses,
            machine.state_param.name,
            machine.selector.field,
        )
        condition_expr = None if clause is None else clause.condition
        event, guard = _split_condition(
            condition_expr,
            state_param=machine.state_param.name,
            selector_field=machine.selector.field,
            source_state=source_state,
            locals_=locals_,
            products=products,
            sums=sums,
        )
        actions = () if clause is None else _actions_in_expr(
            clause.value,
            functions,
            externs,
            aliases,
        )
        action_text = "; ".join(action.call for action in actions) or None
        outcome = (
            "failure"
            if target_state == str(machine_view.get("failure_state", machine.failure))
            else "success"
            if target_state == str(machine_view.get("success_state", machine.success))
            else "normal"
        )
        display = _display_label(event, guard, action_text)
        transition.update(
            {
                "condition_raw": raw_condition,
                "event": event,
                "guard": guard,
                "action": action_text,
                "display_label": display,
                "outcome": outcome,
                "synthesized_failure": False,
                "failure_type": None,
            }
        )
        enriched.append(transition)

        if outcome == "failure":
            continue
        failure_state = str(machine_view.get("failure_state", machine.failure))
        for action in actions:
            if action.error_type is None:
                continue
            key = (source_state, failure_state, action.call, action.error_type)
            if key in seen_failures:
                continue
            seen_failures.add(key)
            failure_action = f"{action.call} ! {action.error_type}"
            failure = dict(transition)
            failure.update(
                {
                    "target_state": failure_state,
                    "action": failure_action,
                    "display_label": _display_label(event, guard, failure_action),
                    "outcome": "failure",
                    "synthesized_failure": True,
                    "failure_type": action.error_type,
                    "expanded_from_wildcard": transition.get("expanded_from_wildcard", False),
                }
            )
            synthesized.append(failure)

    transitions = [*enriched, *synthesized]
    initial = str(machine_view.get("initial_state", ""))
    reachable = _reachable(initial, transitions)
    state_names = [str(item.get("name")) for item in machine_view.get("states", [])]
    unreachable = [name for name in state_names if name not in reachable]
    states = []
    for state in machine_view.get("states", []):
        state_item = dict(state)
        state_item["reachable"] = str(state_item.get("name")) in reachable
        states.append(state_item)

    diagnostics = [
        item
        for item in machine_view.get("diagnostics", [])
        if not (
            item.get("code") == "unreachable-state"
            and any(name in str(item.get("message", "")) for name in reachable)
        )
    ]
    analysis = dict(machine_view.get("analysis", {}))
    analysis.update(
        {
            "normalized_transition_count": len(transitions),
            "reachable_state_count": len(reachable),
            "failure_transition_count": sum(
                1 for item in transitions if item.get("outcome") == "failure"
            ),
            "synthesized_failure_transition_count": len(synthesized),
            "transition_semantics_version": 1,
        }
    )
    machine_view.update(
        {
            "states": states,
            "transitions": transitions,
            "unreachable_states": unreachable,
            "diagnostics": diagnostics,
            "analysis": analysis,
        }
    )
    return machine_view


def enrich_io_state_views(
    model: CompilationModel,
    views: dict[str, object],
) -> dict[str, object]:
    """Add event/guard/action semantics without changing Glyph syntax.

    The pass is conservative: it only extracts an event from a finite sum-type
    input comparison, only displays guards that remain after state/event
    predicates are removed, and only synthesizes a failure edge for an actually
    invoked effect whose declared return type is Result<_, Error>.
    """

    result = deepcopy(views)
    state = dict(result.get("state", {}))
    state["machines"] = [
        _enrich_machine(model, dict(machine))
        for machine in state.get("machines", [])
    ]
    result["state"] = state
    result["transition_semantics_version"] = 1
    return result

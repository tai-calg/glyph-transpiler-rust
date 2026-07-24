from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .compiler import (
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


STATE_TRANSITION_IR_SCHEMA = "glyph.state-transition-ir"
STATE_TRANSITION_IR_VERSION = 2


@dataclass(frozen=True)
class _Action:
    call: str
    failure_type: str | None


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


def _unwrap(expr: Expr) -> Expr:
    if isinstance(expr, TryExpr):
        return _unwrap(expr.expr)
    if (
        isinstance(expr, CallExpr)
        and isinstance(expr.callee, NameExpr)
        and expr.callee.name == "Ok"
        and len(expr.args) == 1
    ):
        return _unwrap(expr.args[0])
    return expr


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


def _failure_type(ty: TypeRef, aliases: Mapping[str, TypeRef]) -> str | None:
    resolved = _resolve_alias(ty, aliases)
    if resolved.name == "R" and len(resolved.args) == 2:
        return _render_type(resolved.args[1])
    return None


def _direct_target(
    expr: Expr,
    *,
    state_decl: ProductDecl,
    selector_index: int,
    variants: set[str],
    state_param: str,
) -> str | None:
    value = _unwrap(expr)
    if isinstance(value, NameExpr) and value.name == state_param:
        return "__same__"
    if not (
        isinstance(value, CallExpr)
        and isinstance(value.callee, NameExpr)
        and value.callee.name == state_decl.name
        and len(value.args) == len(state_decl.fields)
    ):
        return None
    selected = value.args[selector_index]
    if isinstance(selected, NameExpr) and selected.name in variants:
        return selected.name
    return None


def _flatten_and(expr: Expr) -> list[Expr]:
    if isinstance(expr, BinaryExpr) and expr.op == "&":
        return [*_flatten_and(expr.left), *_flatten_and(expr.right)]
    return [expr]


def _selector_sources(
    condition: Expr | None,
    *,
    state_param: str,
    selector_field: str,
    variants: set[str],
) -> set[str]:
    if condition is None:
        return set()
    found: set[str] = set()
    for item in _flatten_and(condition):
        if not isinstance(item, BinaryExpr) or item.op != "==":
            continue
        for left, right in ((item.left, item.right), (item.right, item.left)):
            if (
                isinstance(left, FieldExpr)
                and isinstance(left.base, NameExpr)
                and left.base.name == state_param
                and left.field == selector_field
                and isinstance(right, NameExpr)
                and right.name in variants
            ):
                found.add(right.name)
    return found


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


def _is_selector_predicate(
    expr: Expr,
    *,
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
    *,
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
        declaration = sums.get(type_ref.name)
        if declaration is not None and variant in {item.name for item in declaration.variants}:
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
    parts = _flatten_and(condition)
    remaining: list[Expr] = []
    events: list[str] = []
    for part in parts:
        if _is_selector_predicate(
            part,
            state_param=state_param,
            selector_field=selector_field,
            source_state=source_state,
        ):
            continue
        event = _event_variant(
            part,
            locals_=locals_,
            products=products,
            sums=sums,
            state_param=state_param,
        )
        if event is None:
            remaining.append(part)
        else:
            events.append(event)
    if len(events) > 1:
        return None, "&".join(render_expr(part) for part in parts)
    guard = "&".join(render_expr(part) for part in remaining) or None
    return (events[0] if events else None), guard


def _actions_in_expr(
    expr: Expr,
    *,
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
            action = _Action(
                f"{name}({','.join(render_expr(argument) for argument in item.args)})",
                _failure_type(external.return_type, aliases),
            )
            if action not in actions:
                actions.append(action)
            continue
        nested = functions.get(name)
        if nested is None or nested.guards or nested.expression is None or name in visited:
            continue
        for action in _actions_in_expr(
            nested.expression,
            functions=functions,
            externs=externs,
            aliases=aliases,
            visited={*visited, name},
        ):
            if action not in actions:
                actions.append(action)
    return tuple(actions)


def _display_label(
    event: str | None,
    guard: str | None,
    action: str | None,
    failure_type: str | None = None,
) -> str:
    label = event or ""
    if guard:
        label += f" [{guard}]" if label else f"[{guard}]"
    if action:
        label += f" / {action}" if label else f"/ {action}"
    if failure_type:
        label += f" | {failure_type}"
    return label


def _reachable(initial: str, transitions: Sequence[dict[str, object]]) -> set[str]:
    reachable = {initial}
    changed = True
    while changed:
        changed = False
        for transition in transitions:
            source = str(transition.get("source_state", ""))
            target = str(transition.get("target_state", ""))
            if source in reachable and target not in reachable:
                reachable.add(target)
                changed = True
    return reachable


def _deduplicate(transitions: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for transition in transitions:
        source = transition.get("source", {})
        source_line = source.get("line") if isinstance(source, dict) else None
        key = (
            transition.get("source_state"),
            transition.get("target_state"),
            transition.get("event"),
            transition.get("guard"),
            transition.get("action"),
            transition.get("failure_type"),
            transition.get("outcome"),
            source_line,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(transition))
    return result

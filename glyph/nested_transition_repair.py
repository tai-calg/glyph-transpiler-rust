from __future__ import annotations

from copy import deepcopy
from typing import Iterable, Mapping

from .artifacts import CompilationModel
from .compiler import (
    BinaryExpr,
    CallExpr,
    Expr,
    FieldExpr,
    FunctionDecl,
    NameExpr,
    ProductDecl,
    SumDecl,
    TryExpr,
    UnaryExpr,
)
from .execution_ir import render_expr


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


def _nested_target(
    expr: Expr,
    *,
    functions: Mapping[str, FunctionDecl],
    state_decl: ProductDecl,
    selector_index: int,
    variants: set[str],
    state_param: str,
    visited: set[str] | None = None,
) -> str | None:
    direct = _direct_target(
        expr,
        state_decl=state_decl,
        selector_index=selector_index,
        variants=variants,
        state_param=state_param,
    )
    if direct is not None:
        return direct

    value = _unwrap(expr)
    if not (
        isinstance(value, CallExpr)
        and isinstance(value.callee, NameExpr)
        and value.callee.name in functions
    ):
        return None
    name = value.callee.name
    visited = set() if visited is None else set(visited)
    if name in visited:
        return None
    visited.add(name)
    declaration = functions[name]
    if declaration.guards or declaration.expression is None:
        return None
    nested_state_param = declaration.params[0].name if declaration.params else state_param
    return _nested_target(
        declaration.expression,
        functions=functions,
        state_decl=state_decl,
        selector_index=selector_index,
        variants=variants,
        state_param=nested_state_param,
        visited=visited,
    )


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
    for item in _walk_expr(condition):
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


def _helper_lines(
    expr: Expr,
    functions: Mapping[str, FunctionDecl],
    visited: set[str] | None = None,
) -> set[int]:
    visited = set() if visited is None else set(visited)
    lines: set[int] = set()
    for name in _called_function_names(expr, functions):
        if name in visited:
            continue
        visited.add(name)
        declaration = functions[name]
        if declaration.guards or declaration.expression is None:
            continue
        lines.add(declaration.line)
        lines.update(_helper_lines(declaration.expression, functions, visited))
    return lines


def repair_nested_transition_targets(
    model: CompilationModel,
    views: dict[str, object],
) -> dict[str, object]:
    """Restore outer guards when a pure helper constructs the next state.

    The base analyzer follows helper functions but represents their direct return as
    a wildcard `next` edge. This pass replaces only those helper edges for which a
    unique state constructor is statically visible. Dynamic or guarded helpers are
    left unchanged rather than guessed.
    """

    result = deepcopy(views)
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

    for machine_view in result.get("state", {}).get("machines", []):
        machine = next(
            (item for item in model.machines if item.name == machine_view.get("name")),
            None,
        )
        if machine is None or not isinstance(machine.selector, FieldExpr):
            continue
        state_decl = products.get(machine.state_param.ty.name)
        if state_decl is None:
            continue
        selector_index = next(
            (
                index
                for index, field in enumerate(state_decl.fields)
                if field.name == machine.selector.field
            ),
            None,
        )
        if selector_index is None:
            continue
        selector_sum = sums.get(state_decl.fields[selector_index].ty.name)
        if selector_sum is None:
            continue
        variants = {item.name for item in selector_sum.variants}
        next_name = (
            machine.next_expr.callee.name
            if isinstance(machine.next_expr, CallExpr)
            and isinstance(machine.next_expr.callee, NameExpr)
            else None
        )
        if next_name is None:
            continue

        repaired: list[dict[str, object]] = []
        remove_lines: set[int] = set()
        for function_name in _function_closure(next_name, functions):
            declaration = functions[function_name]
            state_param = declaration.params[0].name if declaration.params else machine.state_param.name
            for clause in declaration.guards:
                if _direct_target(
                    clause.value,
                    state_decl=state_decl,
                    selector_index=selector_index,
                    variants=variants,
                    state_param=state_param,
                ) is not None:
                    continue
                target = _nested_target(
                    clause.value,
                    functions=functions,
                    state_decl=state_decl,
                    selector_index=selector_index,
                    variants=variants,
                    state_param=state_param,
                )
                if target is None:
                    continue
                helper_lines = _helper_lines(clause.value, functions)
                if not helper_lines:
                    continue
                remove_lines.update(helper_lines)
                sources = _selector_sources(
                    clause.condition,
                    state_param=state_param,
                    selector_field=machine.selector.field,
                    variants=variants,
                )
                source_names = sorted(sources or variants)
                condition = "otherwise" if clause.condition is None else render_expr(clause.condition)
                for source in source_names:
                    repaired.append(
                        {
                            "source_state": source,
                            "target_state": source if target == "__same__" else target,
                            "condition": condition,
                            "source": {"line": clause.line},
                            "expanded_from_wildcard": not bool(sources),
                            "source_reachable": True,
                        }
                    )

        if not repaired:
            continue
        existing = [
            dict(item)
            for item in machine_view.get("transitions", [])
            if not (
                str(item.get("condition")) == "next"
                and int(item.get("source", {}).get("line", 0)) in remove_lines
            )
        ]
        seen = {
            (
                str(item.get("source_state")),
                str(item.get("target_state")),
                str(item.get("condition")),
                int(item.get("source", {}).get("line", 0)),
            )
            for item in existing
        }
        for item in repaired:
            key = (
                str(item["source_state"]),
                str(item["target_state"]),
                str(item["condition"]),
                int(item["source"]["line"]),
            )
            if key not in seen:
                seen.add(key)
                existing.append(item)
        machine_view["transitions"] = existing

    return result

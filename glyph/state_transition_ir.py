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


STATE_TRANSITION_IR_SCHEMA = "glyph.state-transition-ir"
STATE_TRANSITION_IR_VERSION = 2


@dataclass(frozen=True)
class _Action:
    call: str
    failure_type: str | None


@dataclass(frozen=True)
class _ResolvedBranch:
    condition: Expr | None
    value: Expr
    target: str
    state_param: str
    locals: Mapping[str, TypeRef]
    line: int


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


def _resolved_target(
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
    declaration = functions[name]
    if declaration.guards or declaration.expression is None:
        return None
    visited.add(name)
    nested_state_param = declaration.params[0].name if declaration.params else state_param
    return _resolved_target(
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
        roots.extend(clause.value for clause in declaration.guards)
        for root_expr in roots:
            pending.extend(reversed(_called_function_names(root_expr, functions)))
    return tuple(ordered)


def _resolved_branches(
    root: str,
    *,
    functions: Mapping[str, FunctionDecl],
    state_decl: ProductDecl,
    selector_index: int,
    variants: set[str],
) -> tuple[_ResolvedBranch, ...]:
    result: list[_ResolvedBranch] = []
    for name in _function_closure(root, functions):
        declaration = functions[name]
        state_param = declaration.params[0].name if declaration.params else "state"
        locals_ = {parameter.name: parameter.ty for parameter in declaration.params}
        if declaration.guards:
            for clause in declaration.guards:
                target = _resolved_target(
                    clause.value,
                    functions=functions,
                    state_decl=state_decl,
                    selector_index=selector_index,
                    variants=variants,
                    state_param=state_param,
                )
                if target is not None:
                    result.append(
                        _ResolvedBranch(
                            clause.condition,
                            clause.value,
                            target,
                            state_param,
                            locals_,
                            clause.line,
                        )
                    )
            continue
        if declaration.expression is None:
            continue
        target = _resolved_target(
            declaration.expression,
            functions=functions,
            state_decl=state_decl,
            selector_index=selector_index,
            variants=variants,
            state_param=state_param,
        )
        if target is not None:
            result.append(
                _ResolvedBranch(
                    None,
                    declaration.expression,
                    target,
                    state_param,
                    locals_,
                    declaration.line,
                )
            )
    return tuple(result)


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
    remaining: list[Expr] = []
    events: list[str] = []
    parts = _flatten_and(condition)
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
        if event is not None:
            events.append(event)
        else:
            remaining.append(part)
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
        key = (
            transition.get("source_state"),
            transition.get("target_state"),
            transition.get("event"),
            transition.get("guard"),
            transition.get("action"),
            transition.get("failure_type"),
            transition.get("outcome"),
            transition.get("source", {}).get("line"),
        )
        if key not in seen:
            seen.add(key)
            result.append(dict(transition))
    return result


def build_machine_state_transition_ir(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Build canonical transition semantics from validated compiler AST.

    The pass resolves unguarded pure helpers before expanding source states, so an
    outer event or guard is never lost. Effect failures are synthesized only for
    invoked effect boundaries returning Result, and transition identity includes
    event and guard to prevent distinct failure routes from collapsing.
    """

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
    next_name = (
        machine.next_expr.callee.name
        if isinstance(machine.next_expr, CallExpr)
        and isinstance(machine.next_expr.callee, NameExpr)
        else None
    )
    if next_name is None or next_name not in functions:
        return result

    unreachable_lines = set(map(int, result.get("unreachable_branches", [])))
    state_names = [str(item.get("name", "")) for item in result.get("states", [])]
    transitions: list[dict[str, object]] = []

    for branch in _resolved_branches(
        next_name,
        functions=functions,
        state_decl=state_decl,
        selector_index=selector_index,
        variants=variants,
    ):
        if branch.line in unreachable_lines:
            continue
        explicit_sources = _selector_sources(
            branch.condition,
            state_param=branch.state_param,
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
        normal_action = "; ".join(action.call for action in actions) or None

        for source_state in source_names:
            target_state = source_state if branch.target == "__same__" else branch.target
            if source_state not in state_names or target_state not in state_names:
                continue
            event, guard = _split_condition(
                branch.condition,
                state_param=branch.state_param,
                selector_field=machine.selector.field,
                source_state=source_state,
                locals_=branch.locals,
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
                "action": normal_action,
                "failure_type": None,
                "outcome": outcome,
                "display_label": _display_label(event, guard, normal_action),
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
    # Compatibility marker for existing third-party renderers. New code should use
    # `state_transition_ir.version` or each machine's `transition_ir.version`.
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

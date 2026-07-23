from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Mapping, Sequence

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
    TypeRef,
    UnaryExpr,
)
from .execution_ir import MachineTransitionView, MachineView, SourceRef, render_expr


@dataclass(frozen=True)
class _Coverage:
    key: str
    type_name: str
    variants: frozenset[str]


@dataclass(frozen=True)
class _BranchDiagnostic:
    line: int
    type_name: str
    reason: str


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


def _unwrap_state_expr(expr: Expr) -> Expr:
    if isinstance(expr, TryExpr):
        return _unwrap_state_expr(expr.expr)
    if (
        isinstance(expr, CallExpr)
        and isinstance(expr.callee, NameExpr)
        and expr.callee.name == "Ok"
        and len(expr.args) == 1
    ):
        return _unwrap_state_expr(expr.args[0])
    return expr


def _selector_comparison(
    expr: Expr,
    state_param: str,
    selector_field: str,
    variants: set[str],
) -> set[str]:
    found: set[str] = set()
    for item in _walk_expr(expr):
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


def _state_target(
    expr: Expr,
    state_decl: ProductDecl,
    selector_index: int,
    variants: set[str],
    state_param: str,
) -> str | None:
    value = _unwrap_state_expr(expr)
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


def _called_functions(
    expr: Expr,
    functions: Mapping[str, FunctionDecl],
) -> tuple[str, ...]:
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


def _declaration_calls(
    declaration: FunctionDecl,
    functions: Mapping[str, FunctionDecl],
) -> tuple[str, ...]:
    names: list[str] = []
    roots: list[Expr] = []
    if declaration.expression is not None:
        roots.append(declaration.expression)
    for clause in declaration.guards:
        if clause.condition is not None:
            roots.append(clause.condition)
        roots.append(clause.value)
    for root in roots:
        for name in _called_functions(root, functions):
            if name not in names:
                names.append(name)
    return tuple(names)


def _function_closure(
    root: str,
    functions: Mapping[str, FunctionDecl],
) -> tuple[str, ...]:
    ordered: list[str] = []
    pending = [root]
    seen: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen or name not in functions:
            continue
        seen.add(name)
        ordered.append(name)
        pending.extend(reversed(_declaration_calls(functions[name], functions)))
    return tuple(ordered)


def _trace_transition_function(
    name: str,
    functions: Mapping[str, FunctionDecl],
    state_decl: ProductDecl,
    selector_index: int,
    selector_field: str,
    variants: set[str],
    visited: set[str],
) -> list[MachineTransitionView]:
    if name in visited or name not in functions:
        return []
    visited = {*visited, name}
    declaration = functions[name]
    state_param = declaration.params[0].name if declaration.params else "state"
    transitions: list[MachineTransitionView] = []

    if declaration.guards:
        for clause in declaration.guards:
            target = _state_target(
                clause.value,
                state_decl,
                selector_index,
                variants,
                state_param,
            )
            if target is None:
                for nested_name in _called_functions(clause.value, functions):
                    transitions.extend(
                        _trace_transition_function(
                            nested_name,
                            functions,
                            state_decl,
                            selector_index,
                            selector_field,
                            variants,
                            visited,
                        )
                    )
                continue
            sources = (
                _selector_comparison(
                    clause.condition,
                    state_param,
                    selector_field,
                    variants,
                )
                if clause.condition is not None
                else set()
            )
            if not sources:
                sources = {"*"}
            condition = (
                render_expr(clause.condition)
                if clause.condition is not None
                else "otherwise"
            )
            for source in sorted(sources):
                resolved_target = source if target == "__same__" and source != "*" else target
                if resolved_target == "__same__":
                    resolved_target = "*"
                transitions.append(
                    MachineTransitionView(
                        source,
                        resolved_target,
                        condition,
                        SourceRef(clause.line),
                    )
                )
        return transitions

    if declaration.expression is None:
        return transitions
    target = _state_target(
        declaration.expression,
        state_decl,
        selector_index,
        variants,
        state_param,
    )
    if target is not None:
        return [
            MachineTransitionView(
                "*",
                "*" if target == "__same__" else target,
                "next",
                SourceRef(declaration.line),
            )
        ]
    for nested_name in _called_functions(declaration.expression, functions):
        transitions.extend(
            _trace_transition_function(
                nested_name,
                functions,
                state_decl,
                selector_index,
                selector_field,
                variants,
                visited,
            )
        )
    return transitions


def _operand_type(
    expr: Expr,
    locals_: Mapping[str, TypeRef],
    products: Mapping[str, ProductDecl],
) -> tuple[str, TypeRef] | None:
    if isinstance(expr, NameExpr):
        type_ref = locals_.get(expr.name)
        return None if type_ref is None else (expr.name, type_ref)
    if isinstance(expr, FieldExpr) and isinstance(expr.base, NameExpr):
        base_type = locals_.get(expr.base.name)
        if base_type is None:
            return None
        product = products.get(base_type.name)
        if product is None:
            return None
        field = next((item for item in product.fields if item.name == expr.field), None)
        if field is None:
            return None
        return f"{expr.base.name}.{expr.field}", field.ty
    return None


def _variant_name(expr: Expr) -> str | None:
    if isinstance(expr, NameExpr):
        return expr.name
    if isinstance(expr, CallExpr) and isinstance(expr.callee, NameExpr):
        return expr.callee.name
    return None


def _atomic_coverage(
    condition: Expr,
    locals_: Mapping[str, TypeRef],
    products: Mapping[str, ProductDecl],
    sums: Mapping[str, SumDecl],
) -> _Coverage | None:
    if not isinstance(condition, BinaryExpr) or condition.op != "==":
        return None
    for subject, pattern in ((condition.left, condition.right), (condition.right, condition.left)):
        operand = _operand_type(subject, locals_, products)
        variant = _variant_name(pattern)
        if operand is None or variant is None:
            continue
        key, type_ref = operand
        sum_decl = sums.get(type_ref.name)
        if sum_decl is None:
            continue
        known = {item.name for item in sum_decl.variants}
        if variant in known:
            return _Coverage(key, type_ref.name, frozenset((variant,)))
    return None


def _condition_coverage(
    condition: Expr,
    locals_: Mapping[str, TypeRef],
    products: Mapping[str, ProductDecl],
    sums: Mapping[str, SumDecl],
) -> _Coverage | None:
    atomic = _atomic_coverage(condition, locals_, products, sums)
    if atomic is not None:
        return atomic
    if not isinstance(condition, BinaryExpr) or condition.op != "|":
        return None
    left = _condition_coverage(condition.left, locals_, products, sums)
    right = _condition_coverage(condition.right, locals_, products, sums)
    if left is None or right is None:
        return None
    if left.key != right.key or left.type_name != right.type_name:
        return None
    return _Coverage(left.key, left.type_name, left.variants | right.variants)


def _unreachable_guard_branches(
    closure: Sequence[str],
    functions: Mapping[str, FunctionDecl],
    products: Mapping[str, ProductDecl],
    sums: Mapping[str, SumDecl],
) -> dict[int, _BranchDiagnostic]:
    diagnostics: dict[int, _BranchDiagnostic] = {}
    for name in closure:
        declaration = functions[name]
        if not declaration.guards:
            continue
        locals_ = {parameter.name: parameter.ty for parameter in declaration.params}
        covered: dict[str, set[str]] = {}
        type_by_key: dict[str, str] = {}
        exhaustive: dict[str, str] = {}
        for clause in declaration.guards:
            if exhaustive:
                type_name = next(iter(exhaustive.values()))
                diagnostics.setdefault(
                    clause.line,
                    _BranchDiagnostic(
                        clause.line,
                        type_name,
                        "prior ordered guards already cover every variant",
                    ),
                )
                continue
            if clause.condition is None:
                continue
            coverage = _condition_coverage(clause.condition, locals_, products, sums)
            if coverage is None:
                continue
            known = covered.setdefault(coverage.key, set())
            type_by_key[coverage.key] = coverage.type_name
            if coverage.variants <= known:
                diagnostics.setdefault(
                    clause.line,
                    _BranchDiagnostic(
                        clause.line,
                        coverage.type_name,
                        "the same variants were matched by earlier ordered guards",
                    ),
                )
                continue
            known.update(coverage.variants)
            all_variants = {item.name for item in sums[coverage.type_name].variants}
            if known >= all_variants:
                exhaustive[coverage.key] = type_by_key[coverage.key]
    return diagnostics


def _machine_context(
    model: CompilationModel,
    machine_name: str,
) -> tuple[
    object | None,
    dict[str, ProductDecl],
    dict[str, SumDecl],
    dict[str, FunctionDecl],
    ProductDecl | None,
    int | None,
    set[str],
    str | None,
]:
    machine = next((item for item in model.machines if item.name == machine_name), None)
    products = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, ProductDecl)
    }
    sums = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, SumDecl)
    }
    functions = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, FunctionDecl)
    }
    if machine is None or not isinstance(machine.selector, FieldExpr):
        return machine, products, sums, functions, None, None, set(), None
    state_decl = products.get(machine.state_param.ty.name)
    if state_decl is None:
        return machine, products, sums, functions, None, None, set(), None
    selector_index = next(
        (
            index
            for index, field in enumerate(state_decl.fields)
            if field.name == machine.selector.field
        ),
        None,
    )
    if selector_index is None:
        return machine, products, sums, functions, state_decl, None, set(), None
    selector_sum = sums.get(state_decl.fields[selector_index].ty.name)
    variants = set() if selector_sum is None else {item.name for item in selector_sum.variants}
    next_name = (
        machine.next_expr.callee.name
        if isinstance(machine.next_expr, CallExpr)
        and isinstance(machine.next_expr.callee, NameExpr)
        else None
    )
    return (
        machine,
        products,
        sums,
        functions,
        state_decl,
        selector_index,
        variants,
        next_name,
    )


def _raw_transitions(
    model: CompilationModel,
    machine_view: MachineView,
) -> tuple[list[MachineTransitionView], tuple[str, ...], dict[int, _BranchDiagnostic], int]:
    (
        machine,
        products,
        sums,
        functions,
        state_decl,
        selector_index,
        variants,
        next_name,
    ) = _machine_context(model, machine_view.name)
    if (
        machine is None
        or state_decl is None
        or selector_index is None
        or next_name is None
        or not variants
    ):
        return [], (), {}, machine_view.source.line
    transitions = _trace_transition_function(
        next_name,
        functions,
        state_decl,
        selector_index,
        machine.selector.field,
        variants,
        set(),
    )
    unique: list[MachineTransitionView] = []
    seen: set[tuple[str, str, str, int]] = set()
    for transition in transitions:
        key = (
            transition.source_state,
            transition.target_state,
            transition.condition,
            transition.source.line,
        )
        if key not in seen:
            seen.add(key)
            unique.append(transition)
    closure = _function_closure(next_name, functions)
    unreachable = _unreachable_guard_branches(closure, functions, products, sums)
    next_line = getattr(machine, "next_line", machine_view.source.line)
    return unique, closure, unreachable, next_line


def _expand_transitions(
    raw: Sequence[MachineTransitionView],
    states: Sequence[str],
    unreachable_lines: set[int],
) -> tuple[list[dict[str, object]], int]:
    normalized: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, int]] = set()
    wildcard_count = 0
    for transition in raw:
        if transition.source.line in unreachable_lines:
            continue
        source_names = states if transition.source_state == "*" else (transition.source_state,)
        wildcard = transition.source_state == "*" or transition.target_state == "*"
        if wildcard:
            wildcard_count += 1
        for source_name in source_names:
            target_name = source_name if transition.target_state == "*" else transition.target_state
            if source_name not in states or target_name not in states:
                continue
            key = (source_name, target_name, transition.condition, transition.source.line)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                {
                    "source_state": source_name,
                    "target_state": target_name,
                    "condition": transition.condition,
                    "source": asdict(transition.source),
                    "expanded_from_wildcard": wildcard,
                }
            )
    return normalized, wildcard_count


def _reachable_states(
    initial_state: str,
    transitions: Sequence[dict[str, object]],
) -> set[str]:
    reachable = {initial_state}
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


def analyze_machine(
    model: CompilationModel,
    machine_view: MachineView,
) -> dict[str, object]:
    """Normalize one validated machine before it reaches a renderer.

    Wildcard sources are expanded into concrete state transitions, unreachable
    ordered-guard branches are removed, and reachability is computed from the
    declared initial state. The renderer never receives `*` as a state node.
    """

    raw, closure, unreachable_branches, next_line = _raw_transitions(model, machine_view)
    state_names = tuple(state.name for state in machine_view.states)
    transitions, wildcard_count = _expand_transitions(
        raw,
        state_names,
        set(unreachable_branches),
    )
    reachable = _reachable_states(machine_view.initial_state, transitions)
    unreachable_states = [name for name in state_names if name not in reachable]

    diagnostics: list[dict[str, object]] = []
    for item in sorted(unreachable_branches.values(), key=lambda value: value.line):
        diagnostics.append(
            {
                "severity": "warning",
                "code": "unreachable-branch",
                "message": (
                    f"ordered guard branch is unreachable: {item.reason} "
                    f"for sum type {item.type_name}"
                ),
                "line": item.line,
            }
        )
    for state_name in unreachable_states:
        source = next(
            (state.source for state in machine_view.states if state.name == state_name),
            machine_view.source,
        )
        diagnostics.append(
            {
                "severity": "warning",
                "code": "unreachable-state",
                "message": (
                    f"state {state_name} is unreachable from initial state "
                    f"{machine_view.initial_state}"
                ),
                "line": source.line,
            }
        )
    active_raw = [item for item in raw if item.source.line not in unreachable_branches]
    if active_raw and all(item.source_state == "*" for item in active_raw):
        diagnostics.append(
            {
                "severity": "warning",
                "code": "state-independent-transition",
                "message": (
                    "next-state logic does not constrain any transition by the "
                    f"selector {machine_view.selector}; every active branch applies "
                    "to every state"
                ),
                "line": next_line,
            }
        )
    if not transitions:
        diagnostics.append(
            {
                "severity": "warning",
                "code": "no-static-transitions",
                "message": "no state transition could be derived statically",
                "line": next_line,
            }
        )

    states = []
    for state in machine_view.states:
        item = asdict(state)
        item["reachable"] = state.name in reachable
        states.append(item)
    for transition in transitions:
        transition["source_reachable"] = transition["source_state"] in reachable

    result = asdict(machine_view)
    result.update(
        {
            "states": states,
            "transitions": transitions,
            "unreachable_states": unreachable_states,
            "unreachable_branches": sorted(unreachable_branches),
            "diagnostics": diagnostics,
            "analysis": {
                "function_closure": list(closure),
                "raw_transition_count": len(raw),
                "normalized_transition_count": len(transitions),
                "wildcard_transition_count": wildcard_count,
                "reachable_state_count": len(reachable),
                "state_count": len(state_names),
            },
        }
    )
    return result

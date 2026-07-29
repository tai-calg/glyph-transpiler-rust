from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .artifacts import CompilationModel
from .compiler import (
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    FieldExpr,
    FunctionDecl,
    NameExpr,
    NumberExpr,
    ProductDecl,
    SumDecl,
    TryExpr,
    UnaryExpr,
    parse_expr,
)
from .execution_ir import render_expr
from .function_blocks import FunctionBlockLowering
from .machine import MachineDecl


@dataclass(frozen=True)
class TransitionBranch:
    condition: Expr | None
    value: Expr
    target: str
    line: int


@dataclass(frozen=True)
class PlannedTransitionBranch:
    branch: TransitionBranch
    source_state: str
    target_state: str
    value: Expr


@dataclass(frozen=True)
class MachineBranchContext:
    machine: MachineDecl
    products: Mapping[str, ProductDecl]
    sums: Mapping[str, SumDecl]
    functions: Mapping[str, FunctionDecl]
    state_decl: ProductDecl
    selector_index: int
    selector_variants: frozenset[str]
    next_function: str
    branches: tuple[TransitionBranch, ...]
    next_block: FunctionBlockLowering | None
    constants: frozenset[str]


def substitute_expr(expression: Expr, values: Mapping[str, Expr]) -> Expr:
    if isinstance(expression, NameExpr):
        return values.get(expression.name, expression)
    if isinstance(expression, FieldExpr):
        return FieldExpr(substitute_expr(expression.base, values), expression.field)
    if isinstance(expression, UnaryExpr):
        return UnaryExpr(expression.op, substitute_expr(expression.expr, values))
    if isinstance(expression, BinaryExpr):
        return BinaryExpr(
            expression.op,
            substitute_expr(expression.left, values),
            substitute_expr(expression.right, values),
        )
    if isinstance(expression, CallExpr):
        return CallExpr(
            substitute_expr(expression.callee, values),
            tuple(substitute_expr(argument, values) for argument in expression.args),
        )
    if isinstance(expression, TryExpr):
        return TryExpr(substitute_expr(expression.expr, values))
    return expression


def unwrap_expr(expression: Expr) -> Expr:
    if isinstance(expression, TryExpr):
        return unwrap_expr(expression.expr)
    if (
        isinstance(expression, CallExpr)
        and isinstance(expression.callee, NameExpr)
        and expression.callee.name == "Ok"
        and len(expression.args) == 1
    ):
        return unwrap_expr(expression.args[0])
    return expression


def field_index(state_decl: ProductDecl, selector: FieldExpr | None) -> int | None:
    if selector is None:
        return None
    return next(
        (
            index
            for index, field in enumerate(state_decl.fields)
            if field.name == selector.field
        ),
        None,
    )


def _ground_value(expression: Expr, constants: frozenset[str]) -> bool:
    if isinstance(expression, (BoolExpr, NumberExpr)):
        return True
    if isinstance(expression, NameExpr):
        return expression.name in constants
    if isinstance(expression, CallExpr) and isinstance(expression.callee, NameExpr):
        return expression.callee.name in constants and all(
            _ground_value(argument, constants) for argument in expression.args
        )
    return False


def simplify_expr(
    expression: Expr,
    *,
    products: Mapping[str, ProductDecl],
    constants: frozenset[str],
) -> Expr:
    if isinstance(expression, FieldExpr):
        base = simplify_expr(expression.base, products=products, constants=constants)
        if isinstance(base, CallExpr) and isinstance(base.callee, NameExpr):
            declaration = products.get(base.callee.name)
            if declaration is not None and len(base.args) == len(declaration.fields):
                index = next(
                    (
                        index
                        for index, field in enumerate(declaration.fields)
                        if field.name == expression.field
                    ),
                    None,
                )
                if index is not None:
                    return simplify_expr(
                        base.args[index],
                        products=products,
                        constants=constants,
                    )
        return FieldExpr(base, expression.field)
    if isinstance(expression, TryExpr):
        return TryExpr(
            simplify_expr(expression.expr, products=products, constants=constants)
        )
    if isinstance(expression, UnaryExpr):
        value = simplify_expr(expression.expr, products=products, constants=constants)
        if expression.op == "!" and isinstance(value, BoolExpr):
            return BoolExpr(not value.value)
        return UnaryExpr(expression.op, value)
    if isinstance(expression, CallExpr):
        return CallExpr(
            simplify_expr(expression.callee, products=products, constants=constants),
            tuple(
                simplify_expr(argument, products=products, constants=constants)
                for argument in expression.args
            ),
        )
    if isinstance(expression, BinaryExpr):
        left = simplify_expr(expression.left, products=products, constants=constants)
        right = simplify_expr(expression.right, products=products, constants=constants)
        if expression.op in {"==", "!="}:
            if _ground_value(left, constants) and _ground_value(right, constants):
                equal = left == right
                return BoolExpr(equal if expression.op == "==" else not equal)
        if expression.op == "&":
            if isinstance(left, BoolExpr):
                return right if left.value else BoolExpr(False)
            if isinstance(right, BoolExpr):
                return left if right.value else BoolExpr(False)
        if expression.op == "|":
            if isinstance(left, BoolExpr):
                return BoolExpr(True) if left.value else right
            if isinstance(right, BoolExpr):
                return BoolExpr(True) if right.value else left
        return BinaryExpr(expression.op, left, right)
    return expression


def _unwrap_call(expression: Expr) -> CallExpr | None:
    value = unwrap_expr(expression)
    return value if isinstance(value, CallExpr) else None


def _combine(left: Expr | None, right: Expr | None) -> Expr | None:
    if left is None:
        return right
    if right is None:
        return left
    return BinaryExpr("&", left, right)


def _call_bindings(
    declaration: FunctionDecl,
    call: CallExpr,
) -> dict[str, Expr] | None:
    if len(declaration.params) != len(call.args):
        return None
    return {
        parameter.name: argument
        for parameter, argument in zip(declaration.params, call.args, strict=True)
    }


def _inline_unguarded(
    expression: Expr,
    functions: Mapping[str, FunctionDecl],
    visited: frozenset[str] = frozenset(),
) -> Expr:
    if isinstance(expression, UnaryExpr):
        return UnaryExpr(
            expression.op,
            _inline_unguarded(expression.expr, functions, visited),
        )
    if isinstance(expression, TryExpr):
        return TryExpr(_inline_unguarded(expression.expr, functions, visited))
    if isinstance(expression, BinaryExpr):
        return BinaryExpr(
            expression.op,
            _inline_unguarded(expression.left, functions, visited),
            _inline_unguarded(expression.right, functions, visited),
        )
    if isinstance(expression, FieldExpr):
        return FieldExpr(
            _inline_unguarded(expression.base, functions, visited),
            expression.field,
        )
    if not isinstance(expression, CallExpr):
        return expression

    callee = _inline_unguarded(expression.callee, functions, visited)
    arguments = tuple(
        _inline_unguarded(argument, functions, visited)
        for argument in expression.args
    )
    call = CallExpr(callee, arguments)
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
    body = substitute_expr(declaration.expression, bindings)
    return _inline_unguarded(body, functions, visited | {declaration.name})


def _direct_target(
    expression: Expr,
    *,
    state_decl: ProductDecl,
    selector_index: int,
    variants: frozenset[str],
    state_param: str,
) -> str | None:
    value = unwrap_expr(expression)
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


def _trace_function(
    name: str,
    *,
    functions: Mapping[str, FunctionDecl],
    state_decl: ProductDecl,
    selector_index: int,
    variants: frozenset[str],
    root_state_param: str,
    bindings: Mapping[str, Expr],
    inherited_condition: Expr | None,
    visited: tuple[str, ...],
) -> list[TransitionBranch]:
    if name in visited:
        return []
    declaration = functions.get(name)
    if declaration is None:
        return []
    next_visited = (*visited, name)
    branches: list[TransitionBranch] = []

    def trace_value(value: Expr, condition: Expr | None, line: int) -> None:
        substituted = substitute_expr(value, bindings)
        inlined = _inline_unguarded(substituted, functions)
        target = _direct_target(
            inlined,
            state_decl=state_decl,
            selector_index=selector_index,
            variants=variants,
            state_param=root_state_param,
        )
        if target is not None:
            branches.append(TransitionBranch(condition, inlined, target, line))
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
                None
                if clause.condition is None
                else substitute_expr(clause.condition, bindings),
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
    variants: frozenset[str],
    root_state_param: str,
) -> tuple[TransitionBranch, ...]:
    declaration = functions.get(root)
    if declaration is None:
        return ()
    identity = {
        parameter.name: NameExpr(parameter.name)
        for parameter in declaration.params
    }
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


def build_machine_branch_context(
    model: CompilationModel,
    machine_name: str,
) -> MachineBranchContext | None:
    machine = next((item for item in model.machines if item.name == machine_name), None)
    if machine is None or not isinstance(machine.selector, FieldExpr):
        return None
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
    state_decl = products.get(machine.state_param.ty.name)
    if state_decl is None:
        return None
    selector_index = field_index(state_decl, machine.selector)
    if selector_index is None:
        return None
    selector_sum = sums.get(state_decl.fields[selector_index].ty.name)
    if selector_sum is None:
        return None
    next_expression = unwrap_expr(machine.next_expr)
    if not (
        isinstance(next_expression, CallExpr)
        and isinstance(next_expression.callee, NameExpr)
    ):
        return None
    next_function = next_expression.callee.name
    selector_variants = frozenset(item.name for item in selector_sum.variants)
    constants = frozenset(
        variant.name
        for declaration in sums.values()
        for variant in declaration.variants
    )
    return MachineBranchContext(
        machine=machine,
        products=products,
        sums=sums,
        functions=functions,
        state_decl=state_decl,
        selector_index=selector_index,
        selector_variants=selector_variants,
        next_function=next_function,
        branches=_root_branches(
            next_function,
            functions=functions,
            state_decl=state_decl,
            selector_index=selector_index,
            variants=selector_variants,
            root_state_param=machine.state_param.name,
        ),
        next_block=next(
            (item for item in model.blocks if item.name == next_function),
            None,
        ),
        constants=constants,
    )


def _source_state_value(
    context: MachineBranchContext,
    source_state: str,
) -> Expr:
    state_name = context.machine.state_param.name
    arguments = tuple(
        NameExpr(source_state)
        if index == context.selector_index
        else FieldExpr(NameExpr(state_name), field.name)
        for index, field in enumerate(context.state_decl.fields)
    )
    return CallExpr(NameExpr(context.state_decl.name), arguments)


def specialize_for_source(
    context: MachineBranchContext,
    expression: Expr,
    source_state: str,
) -> Expr:
    substituted = substitute_expr(
        expression,
        {
            context.machine.state_param.name: _source_state_value(
                context,
                source_state,
            )
        },
    )
    return simplify_expr(
        substituted,
        products=context.products,
        constants=context.constants,
    )


def _conditional_block_values(
    block: FunctionBlockLowering | None,
) -> tuple[tuple[int, str, Expr], ...]:
    if block is None:
        return ()
    values: list[tuple[int, str, Expr]] = []
    for binding in block.bindings:
        if binding.kind != "conditional":
            continue
        for offset, original in enumerate(binding.source.splitlines(), start=1):
            stripped = original.strip()
            arrow = stripped.find("=>")
            if arrow < 0:
                continue
            condition_text = stripped[:arrow].strip()
            value_text = stripped[arrow + 2 :].strip()
            if not value_text:
                continue
            try:
                value = parse_expr(value_text)
                condition = (
                    "otherwise"
                    if condition_text == "_"
                    else render_expr(parse_expr(condition_text))
                )
            except Exception:
                continue
            values.append((binding.line + offset, condition, value))
    return tuple(values)


def _block_value_for_transition(
    context: MachineBranchContext,
    transition: Mapping[str, object],
) -> Expr | None:
    values = _conditional_block_values(context.next_block)
    source = transition.get("source", {})
    line = int(source.get("line", 0)) if isinstance(source, Mapping) else 0
    raw = str(transition.get("condition_raw") or transition.get("condition") or "")
    condition = "otherwise" if raw in {"", "otherwise", "next"} else raw
    exact = [
        value
        for candidate_line, candidate_condition, value in values
        if candidate_line == line and candidate_condition == condition
    ]
    if exact:
        return exact[0]
    matching = [
        value
        for _, candidate_condition, value in values
        if candidate_condition == condition
    ]
    return matching[0] if len(matching) == 1 else None


def branch_value_for_transition(
    context: MachineBranchContext,
    transition: Mapping[str, object],
    branch_plan: Sequence[PlannedTransitionBranch],
) -> Expr | None:
    source = transition.get("source", {})
    line = int(source.get("line", 0)) if isinstance(source, Mapping) else 0
    source_state = str(transition.get("source_state") or "")
    target_state = str(transition.get("target_state") or "")
    candidates = [
        item
        for item in branch_plan
        if item.branch.line == line and item.source_state == source_state
    ]
    if bool(transition.get("synthesized_failure")) and candidates:
        return candidates[0].value
    exact = [item.value for item in candidates if item.target_state == target_state]
    if exact:
        return exact[0]
    if len(candidates) == 1:
        return candidates[0].value
    block_value = _block_value_for_transition(context, transition)
    if block_value is None or not source_state:
        return block_value
    return specialize_for_source(context, block_value, source_state)

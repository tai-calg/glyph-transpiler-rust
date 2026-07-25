from __future__ import annotations

from dataclasses import dataclass
from itertools import product as cartesian_product
from typing import Mapping, Sequence

from .compiler import (
    AliasDecl,
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    FieldExpr,
    FunctionDecl,
    NameExpr,
    NumberExpr,
    ProductDecl,
    Program,
    SumDecl,
    TryExpr,
    TypeRef,
    UnaryExpr,
)
from .execution_ir import ExecutionStructureIR, render_expr
from .machine import MachineDecl
from .pipeline import _render_type


_DEFAULT_COVERAGE_LIMIT = 256
_OPTION_NAMES = {"O", "Option"}
_RESULT_NAMES = {"R", "Result"}


@dataclass(frozen=True)
class FiniteValue:
    type_name: str
    kind: str
    display: str
    scalar: bool | int | float | None = None
    variant: str | None = None
    fields: tuple[tuple[str, "FiniteValue"], ...] = ()

    def field(self, name: str) -> "FiniteValue | None":
        return next((value for key, value in self.fields if key == name), None)

    def canonical(self) -> tuple[object, ...]:
        return (
            self.kind,
            self.type_name,
            self.scalar,
            self.variant,
            tuple((name, value.canonical()) for name, value in self.fields),
        )


@dataclass(frozen=True)
class CoverageBinding:
    name: str
    value: str


@dataclass(frozen=True)
class MachineCoverageCase:
    index: int
    selector: str
    inputs: tuple[CoverageBinding, ...]
    outcome: str
    selected_clause: int | None
    matching_clauses: tuple[int, ...]
    target_state: str | None
    line: int | None
    reason: str | None


@dataclass(frozen=True)
class MachineGuardCoverage:
    index: int
    line: int
    condition: str
    true_cases: int
    first_match_cases: int
    shadowed_cases: int
    unknown_cases: int
    unreachable: bool
    classification: str


@dataclass(frozen=True)
class MachineCoverage:
    machine: str
    state_type: str
    input_types: tuple[str, ...]
    state_cardinality: str | None
    input_cardinality: str | None
    possible_pairs: str | None
    defined_pairs: int
    missing_pairs: str | None
    complete: bool | None
    reason: str | None
    domain_semantics: str = "selector×input"
    selector_field: str | None = None
    selector_type: str | None = None
    selector_cardinality: str | None = None
    rejected_pairs: int = 0
    fallthrough_pairs: int = 0
    overlap_pairs: int = 0
    unknown_pairs: int = 0
    exact: bool = False
    cases: tuple[MachineCoverageCase, ...] = ()
    guards: tuple[MachineGuardCoverage, ...] = ()


@dataclass(frozen=True)
class _VariantSymbol:
    name: str


@dataclass(frozen=True)
class _Unknown:
    reason: str


_UNKNOWN = _Unknown("unknown")


class _FiniteDomain:
    def __init__(self, program: Program, limit: int):
        self.limit = limit
        self.products = {
            declaration.name: declaration
            for declaration in program.declarations
            if isinstance(declaration, ProductDecl)
        }
        self.sums = {
            declaration.name: declaration
            for declaration in program.declarations
            if isinstance(declaration, SumDecl)
        }
        self.aliases = {
            declaration.name: declaration
            for declaration in program.declarations
            if isinstance(declaration, AliasDecl)
        }
        self.cache: dict[str, tuple[FiniteValue, ...] | None] = {}

    def values_for_ref(
        self,
        ty: TypeRef,
        stack: tuple[str, ...] = (),
    ) -> tuple[FiniteValue, ...] | None:
        if not ty.args and ty.name in self.products:
            return self.values_for_name(ty.name, stack)
        if not ty.args and ty.name in self.sums:
            return self.values_for_name(ty.name, stack)
        if not ty.args and ty.name in self.aliases:
            return self.values_for_name(ty.name, stack)
        if ty.name in {"bool", "B"} and not ty.args:
            return (
                FiniteValue("bool", "scalar", "false", scalar=False),
                FiniteValue("bool", "scalar", "true", scalar=True),
            )
        if ty.name in {"()", "Unit"} and not ty.args:
            return (FiniteValue(ty.name, "unit", "()"),)
        if ty.name == "Never" and not ty.args:
            return ()
        if ty.name == "tuple":
            factors = [self.values_for_ref(argument, stack) for argument in ty.args]
            combinations = self._product(factors)
            if combinations is None:
                return None
            return tuple(
                FiniteValue(
                    _render_type(ty),
                    "tuple",
                    "(" + ", ".join(item.display for item in values) + ("," if len(values) == 1 else "") + ")",
                    fields=tuple((str(index), item) for index, item in enumerate(values)),
                )
                for values in combinations
            )
        if ty.name in _OPTION_NAMES and len(ty.args) == 1:
            inner = self.values_for_ref(ty.args[0], stack)
            if inner is None or len(inner) + 1 > self.limit:
                return None
            type_name = _render_type(ty)
            return (
                FiniteValue(type_name, "variant", "None", variant="None"),
                *(
                    FiniteValue(
                        type_name,
                        "variant",
                        f"Some({value.display})",
                        variant="Some",
                        fields=(("0", value),),
                    )
                    for value in inner
                ),
            )
        if ty.name in _RESULT_NAMES and len(ty.args) == 2:
            ok_values = self.values_for_ref(ty.args[0], stack)
            error_values = self.values_for_ref(ty.args[1], stack)
            if ok_values is None or error_values is None:
                return None
            if len(ok_values) + len(error_values) > self.limit:
                return None
            type_name = _render_type(ty)
            return tuple(
                [
                    *(
                        FiniteValue(
                            type_name,
                            "variant",
                            f"Ok({value.display})",
                            variant="Ok",
                            fields=(("0", value),),
                        )
                        for value in ok_values
                    ),
                    *(
                        FiniteValue(
                            type_name,
                            "variant",
                            f"Err({value.display})",
                            variant="Err",
                            fields=(("0", value),),
                        )
                        for value in error_values
                    ),
                ]
            )
        return None

    def values_for_name(
        self,
        name: str,
        stack: tuple[str, ...] = (),
    ) -> tuple[FiniteValue, ...] | None:
        if not stack and name in self.cache:
            return self.cache[name]
        if name in stack:
            return None
        next_stack = (*stack, name)
        if name in self.aliases:
            result = self.values_for_ref(self.aliases[name].target, next_stack)
        elif name in self.products:
            declaration = self.products[name]
            combinations = self._product(
                [self.values_for_ref(field.ty, next_stack) for field in declaration.fields]
            )
            result = (
                None
                if combinations is None
                else tuple(
                    FiniteValue(
                        name,
                        "product",
                        f"{name} {{ "
                        + ", ".join(
                            f"{field.name}: {value.display}"
                            for field, value in zip(declaration.fields, values)
                        )
                        + " }",
                        fields=tuple(
                            (field.name, value)
                            for field, value in zip(declaration.fields, values)
                        ),
                    )
                    for values in combinations
                )
            )
        elif name in self.sums:
            declaration = self.sums[name]
            output: list[FiniteValue] = []
            for variant in declaration.variants:
                payload = (
                    list(variant.tuple_types)
                    if variant.tuple_types
                    else [field.ty for field in variant.fields]
                )
                combinations = self._product(
                    [self.values_for_ref(ty, next_stack) for ty in payload]
                )
                if combinations is None:
                    result = None
                    break
                for values in combinations:
                    if variant.tuple_types:
                        fields = tuple((str(index), value) for index, value in enumerate(values))
                        display = f"{name}::{variant.name}(" + ", ".join(
                            value.display for value in values
                        ) + ")"
                    elif variant.fields:
                        fields = tuple(
                            (field.name, value)
                            for field, value in zip(variant.fields, values)
                        )
                        display = f"{name}::{variant.name} {{ " + ", ".join(
                            f"{field.name}: {value.display}"
                            for field, value in zip(variant.fields, values)
                        ) + " }"
                    else:
                        fields = ()
                        display = f"{name}::{variant.name}"
                    output.append(
                        FiniteValue(
                            name,
                            "variant",
                            display,
                            variant=variant.name,
                            fields=fields,
                        )
                    )
                    if len(output) > self.limit:
                        result = None
                        break
                else:
                    continue
                break
            else:
                result = tuple(output)
        else:
            result = None
        if not stack:
            self.cache[name] = result
        return result

    def _product(
        self,
        factors: Sequence[tuple[FiniteValue, ...] | None],
    ) -> tuple[tuple[FiniteValue, ...], ...] | None:
        if any(factor is None for factor in factors):
            return None
        exact = [factor for factor in factors if factor is not None]
        cardinality = 1
        for factor in exact:
            cardinality *= len(factor)
            if cardinality > self.limit:
                return None
        return tuple(cartesian_product(*exact)) if exact else ((),)


def _truth(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, FiniteValue) and value.kind == "scalar" and isinstance(value.scalar, bool):
        return value.scalar
    return None


def _equal(left: object, right: object) -> bool | None:
    if isinstance(left, _Unknown) or isinstance(right, _Unknown):
        return None
    if isinstance(left, FiniteValue) and isinstance(right, FiniteValue):
        return left.canonical() == right.canonical()
    if isinstance(left, FiniteValue) and isinstance(right, _VariantSymbol):
        return left.variant == right.name if left.variant is not None else None
    if isinstance(right, FiniteValue) and isinstance(left, _VariantSymbol):
        return right.variant == left.name if right.variant is not None else None
    if isinstance(left, _VariantSymbol) and isinstance(right, _VariantSymbol):
        return left.name == right.name
    if isinstance(left, FiniteValue) and left.kind == "scalar":
        return left.scalar == right
    if isinstance(right, FiniteValue) and right.kind == "scalar":
        return right.scalar == left
    if isinstance(left, (bool, int, float)) and isinstance(right, (bool, int, float)):
        return left == right
    return None


def _numeric(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, FiniteValue) and isinstance(value.scalar, (int, float)) and not isinstance(value.scalar, bool):
        return value.scalar
    return None


def _eval_expr(expr: Expr, environment: Mapping[str, object]) -> object:
    if isinstance(expr, BoolExpr):
        return expr.value
    if isinstance(expr, NumberExpr):
        return float(expr.value) if "." in expr.value else int(expr.value)
    if isinstance(expr, NameExpr):
        return environment.get(expr.name, _VariantSymbol(expr.name))
    if isinstance(expr, FieldExpr):
        base = _eval_expr(expr.base, environment)
        if isinstance(base, FiniteValue):
            return base.field(expr.field) or _Unknown(f"unknown field {expr.field}")
        return _Unknown(f"field access on unknown value: {expr.field}")
    if isinstance(expr, TryExpr):
        return _Unknown("try expression is not a pure guard value")
    if isinstance(expr, CallExpr):
        return _Unknown("function call in guard")
    if isinstance(expr, UnaryExpr):
        value = _eval_expr(expr.expr, environment)
        if expr.op == "!":
            truth = _truth(value)
            return _Unknown("unknown boolean operand") if truth is None else not truth
        if expr.op == "-":
            number = _numeric(value)
            return _Unknown("unknown numeric operand") if number is None else -number
        return _Unknown(f"unsupported unary operator {expr.op}")
    if not isinstance(expr, BinaryExpr):
        return _UNKNOWN

    left = _eval_expr(expr.left, environment)
    if expr.op == "&":
        left_truth = _truth(left)
        if left_truth is False:
            return False
        right_truth = _truth(_eval_expr(expr.right, environment))
        if left_truth is True:
            return right_truth if right_truth is not None else _Unknown("unknown right operand")
        if right_truth is False:
            return False
        return _Unknown("unknown conjunction")
    if expr.op == "|":
        left_truth = _truth(left)
        if left_truth is True:
            return True
        right_truth = _truth(_eval_expr(expr.right, environment))
        if left_truth is False:
            return right_truth if right_truth is not None else _Unknown("unknown right operand")
        if right_truth is True:
            return True
        return _Unknown("unknown disjunction")

    right = _eval_expr(expr.right, environment)
    if expr.op in {"==", "="}:
        result = _equal(left, right)
        return _Unknown("unknown equality") if result is None else result
    if expr.op == "!=":
        result = _equal(left, right)
        return _Unknown("unknown inequality") if result is None else not result

    left_number = _numeric(left)
    right_number = _numeric(right)
    if left_number is None or right_number is None:
        return _Unknown(f"unknown numeric operands for {expr.op}")
    if expr.op == "<":
        return left_number < right_number
    if expr.op == "<=":
        return left_number <= right_number
    if expr.op == ">":
        return left_number > right_number
    if expr.op == ">=":
        return left_number >= right_number
    if expr.op == "+":
        return left_number + right_number
    if expr.op == "-":
        return left_number - right_number
    if expr.op == "*":
        return left_number * right_number
    if expr.op == "/":
        if right_number == 0:
            return _Unknown("division by zero")
        return left_number / right_number
    return _Unknown(f"unsupported operator {expr.op}")


def _unwrap_result(expr: Expr) -> tuple[str | None, Expr]:
    value = expr
    while isinstance(value, TryExpr):
        value = value.expr
    if (
        isinstance(value, CallExpr)
        and isinstance(value.callee, NameExpr)
        and value.callee.name in {"Ok", "Err"}
        and len(value.args) == 1
    ):
        return value.callee.name, value.args[0]
    return None, value


def _target_state(
    expr: Expr,
    state_decl: ProductDecl,
    selector_index: int,
    state_param: str,
    current_selector: FiniteValue,
) -> str | None:
    wrapper, value = _unwrap_result(expr)
    if wrapper == "Err":
        return None
    if isinstance(value, NameExpr) and value.name == state_param:
        return current_selector.variant or current_selector.display
    if not (
        isinstance(value, CallExpr)
        and isinstance(value.callee, NameExpr)
        and value.callee.name == state_decl.name
        and len(value.args) == len(state_decl.fields)
    ):
        return None
    selected = value.args[selector_index]
    if isinstance(selected, NameExpr):
        if selected.name == state_param:
            return current_selector.variant or current_selector.display
        return selected.name
    if (
        isinstance(selected, FieldExpr)
        and isinstance(selected.base, NameExpr)
        and selected.base.name == state_param
    ):
        return current_selector.variant or current_selector.display
    return None


def _machine_parts(
    program: Program,
    machine: MachineDecl,
) -> tuple[ProductDecl, int, str, SumDecl, FunctionDecl] | None:
    products = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, ProductDecl)
    }
    sums = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, SumDecl)
    }
    functions = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, FunctionDecl)
    }
    state_decl = products.get(machine.state_param.ty.name)
    selector = machine.selector
    if state_decl is None or not isinstance(selector, FieldExpr):
        return None
    selector_index = next(
        (index for index, field in enumerate(state_decl.fields) if field.name == selector.field),
        None,
    )
    if selector_index is None:
        return None
    selector_type = state_decl.fields[selector_index].ty
    selector_sum = sums.get(selector_type.name)
    next_call = machine.next_expr
    if not (
        selector_sum is not None
        and isinstance(next_call, CallExpr)
        and isinstance(next_call.callee, NameExpr)
    ):
        return None
    next_decl = functions.get(next_call.callee.name)
    if next_decl is None:
        return None
    return state_decl, selector_index, selector.field, selector_sum, next_decl


def _function_environment(
    machine: MachineDecl,
    next_decl: FunctionDecl,
    selector_field: str,
    selector_value: FiniteValue,
    input_values: Mapping[str, FiniteValue],
) -> dict[str, object]:
    machine_environment: dict[str, object] = dict(input_values)
    machine_environment[machine.state_param.name] = FiniteValue(
        machine.state_param.ty.name,
        "product",
        f"{machine.state_param.name}{{{selector_field}={selector_value.display}}}",
        fields=((selector_field, selector_value),),
    )
    next_call = machine.next_expr
    assert isinstance(next_call, CallExpr)
    environment: dict[str, object] = {}
    for parameter, argument in zip(next_decl.params, next_call.args):
        environment[parameter.name] = _eval_expr(argument, machine_environment)
    return environment


def _clauses(declaration: FunctionDecl) -> tuple[tuple[Expr | None, Expr, int, bool], ...]:
    if declaration.guards:
        return tuple(
            (clause.condition, clause.value, clause.line, clause.condition is None)
            for clause in declaration.guards
        )
    if declaration.expression is not None:
        return ((None, declaration.expression, declaration.line, False),)
    return ()


def _unknown_coverage(
    machine: MachineDecl,
    state_type: str,
    input_types: tuple[str, ...],
    selector_field: str | None,
    selector_type: str | None,
    reason: str,
) -> MachineCoverage:
    return MachineCoverage(
        machine=machine.name,
        state_type=state_type,
        input_types=input_types,
        state_cardinality=None,
        input_cardinality=None,
        possible_pairs=None,
        defined_pairs=0,
        missing_pairs=None,
        complete=None,
        reason=reason,
        selector_field=selector_field,
        selector_type=selector_type,
        selector_cardinality=None,
        exact=False,
    )


def build_machine_coverage(
    program: Program,
    machines: Sequence[MachineDecl],
    execution_ir: ExecutionStructureIR,
    algebra: object,
    *,
    coverage_limit: int = _DEFAULT_COVERAGE_LIMIT,
) -> tuple[MachineCoverage, ...]:
    del execution_ir, algebra
    if coverage_limit < 1:
        raise ValueError("coverage_limit must be positive")
    domain = _FiniteDomain(program, coverage_limit)
    rows: list[MachineCoverage] = []

    for machine in machines:
        input_types = tuple(_render_type(parameter.ty) for parameter in machine.input_params)
        parts = _machine_parts(program, machine)
        if parts is None:
            rows.append(
                _unknown_coverage(
                    machine,
                    machine.state_param.ty.name,
                    input_types,
                    None,
                    None,
                    "selector or next function could not be resolved",
                )
            )
            continue
        state_decl, selector_index, selector_field, selector_sum, next_decl = parts
        selector_values = domain.values_for_name(selector_sum.name)
        if selector_values is None:
            rows.append(
                _unknown_coverage(
                    machine,
                    state_decl.name,
                    input_types,
                    selector_field,
                    selector_sum.name,
                    "selector domain is not finitely enumerable within the coverage limit",
                )
            )
            continue
        input_domains = [domain.values_for_ref(parameter.ty) for parameter in machine.input_params]
        if any(values is None for values in input_domains):
            rows.append(
                _unknown_coverage(
                    machine,
                    state_decl.name,
                    input_types,
                    selector_field,
                    selector_sum.name,
                    "one or more input domains are not finitely enumerable within the coverage limit",
                )
            )
            continue
        exact_inputs = [values for values in input_domains if values is not None]
        input_cardinality = 1
        for values in exact_inputs:
            input_cardinality *= len(values)
        possible = len(selector_values) * input_cardinality
        if possible > coverage_limit:
            rows.append(
                MachineCoverage(
                    machine=machine.name,
                    state_type=state_decl.name,
                    input_types=input_types,
                    state_cardinality=str(len(selector_values)),
                    input_cardinality=str(input_cardinality),
                    possible_pairs=str(possible),
                    defined_pairs=0,
                    missing_pairs=None,
                    complete=None,
                    reason=f"selector×input domain exceeds coverage limit {coverage_limit}",
                    selector_field=selector_field,
                    selector_type=selector_sum.name,
                    selector_cardinality=str(len(selector_values)),
                    exact=False,
                )
            )
            continue

        clauses = _clauses(next_decl)
        guard_true = [0] * len(clauses)
        guard_first = [0] * len(clauses)
        guard_shadowed = [0] * len(clauses)
        guard_unknown = [0] * len(clauses)
        cases: list[MachineCoverageCase] = []
        counts = {name: 0 for name in ("defined", "rejected", "fallthrough", "missing", "unknown")}
        overlap_pairs = 0
        input_combinations = tuple(cartesian_product(*exact_inputs)) if exact_inputs else ((),)

        for selector_value in selector_values:
            for combination in input_combinations:
                input_values = {
                    parameter.name: value
                    for parameter, value in zip(machine.input_params, combination)
                }
                environment = _function_environment(
                    machine,
                    next_decl,
                    selector_field,
                    selector_value,
                    input_values,
                )
                evaluations: list[bool | None] = []
                explicit_true: list[int] = []
                for index, (condition, _, _, is_default) in enumerate(clauses):
                    if condition is None:
                        evaluations.append(True if not is_default else None)
                        continue
                    truth = _truth(_eval_expr(condition, environment))
                    evaluations.append(truth)
                    if truth is True:
                        explicit_true.append(index + 1)
                        guard_true[index] += 1
                    elif truth is None:
                        guard_unknown[index] += 1
                if len(explicit_true) > 1:
                    overlap_pairs += 1

                selected: int | None = None
                selection_unknown = False
                unknown_seen = False
                for index, ((condition, _, _, is_default), truth) in enumerate(zip(clauses, evaluations)):
                    if is_default:
                        if unknown_seen:
                            selection_unknown = True
                        else:
                            selected = index
                        break
                    if condition is None:
                        selected = index
                        break
                    if truth is None:
                        unknown_seen = True
                        continue
                    if truth is True:
                        if unknown_seen:
                            selection_unknown = True
                        else:
                            selected = index
                        break
                if selected is None and unknown_seen:
                    selection_unknown = True

                target_state: str | None = None
                line: int | None = None
                reason: str | None = None
                if selection_unknown:
                    outcome = "unknown"
                    reason = "ordered branch selection depends on an unsupported guard"
                elif selected is None:
                    outcome = "missing"
                    reason = "no guard matched and no default clause exists"
                else:
                    _, value, line, is_default = clauses[selected]
                    guard_first[selected] += 1
                    wrapper, _ = _unwrap_result(value)
                    if wrapper == "Err":
                        outcome = "rejected"
                    elif is_default:
                        outcome = "fallthrough"
                    else:
                        outcome = "defined"
                    state_param = next_decl.params[0].name if next_decl.params else "state"
                    target_state = _target_state(
                        value,
                        state_decl,
                        selector_index,
                        state_param,
                        selector_value,
                    )
                counts[outcome] += 1
                cases.append(
                    MachineCoverageCase(
                        index=len(cases),
                        selector=selector_value.display,
                        inputs=tuple(
                            CoverageBinding(parameter.name, value.display)
                            for parameter, value in zip(machine.input_params, combination)
                        ),
                        outcome=outcome,
                        selected_clause=None if selected is None else selected + 1,
                        matching_clauses=tuple(explicit_true),
                        target_state=target_state,
                        line=line,
                        reason=reason,
                    )
                )

        for index in range(len(clauses)):
            guard_shadowed[index] = max(0, guard_true[index] - guard_first[index])
        guard_rows: list[MachineGuardCoverage] = []
        for index, (condition, _, line, is_default) in enumerate(clauses):
            if is_default:
                classification = "default"
                unreachable = guard_first[index] == 0
            elif guard_true[index] == 0 and guard_unknown[index] == 0:
                classification = "unsatisfiable"
                unreachable = True
            elif guard_true[index] > 0 and guard_first[index] == 0:
                classification = "shadowed"
                unreachable = True
            elif guard_first[index] == 0 and guard_unknown[index] > 0:
                classification = "unknown"
                unreachable = False
            else:
                classification = "reachable"
                unreachable = False
            guard_rows.append(
                MachineGuardCoverage(
                    index=index + 1,
                    line=line,
                    condition="otherwise" if is_default else "always" if condition is None else render_expr(condition),
                    true_cases=guard_true[index],
                    first_match_cases=guard_first[index],
                    shadowed_cases=guard_shadowed[index],
                    unknown_cases=guard_unknown[index],
                    unreachable=unreachable,
                    classification=classification,
                )
            )

        missing = counts["missing"]
        unknown = counts["unknown"]
        rows.append(
            MachineCoverage(
                machine=machine.name,
                state_type=state_decl.name,
                input_types=input_types,
                state_cardinality=str(len(selector_values)),
                input_cardinality=str(input_cardinality),
                possible_pairs=str(possible),
                defined_pairs=counts["defined"],
                missing_pairs=str(missing),
                complete=missing == 0 and unknown == 0,
                reason=None,
                selector_field=selector_field,
                selector_type=selector_sum.name,
                selector_cardinality=str(len(selector_values)),
                rejected_pairs=counts["rejected"],
                fallthrough_pairs=counts["fallthrough"],
                overlap_pairs=overlap_pairs,
                unknown_pairs=unknown,
                exact=True,
                cases=tuple(cases),
                guards=tuple(guard_rows),
            )
        )
    return tuple(rows)

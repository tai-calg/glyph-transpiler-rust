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
from .machine_coverage import (
    CoverageBinding,
    FiniteValue,
    MachineCoverage,
    MachineCoverageCase,
    MachineGuardCoverage,
    _FiniteDomain,
    _clauses,
    _eval_expr,
    _function_environment,
    _machine_parts,
    _target_state,
    _truth,
    _unknown_coverage,
    _unwrap_result,
    build_machine_coverage as _build_enumerated_coverage,
)
from .pipeline import _render_type


_DEFAULT_PARTITION_LIMIT = 256
_DEFAULT_MATERIALIZATION_LIMIT = 4096

_INTEGER_BOUNDS: dict[str, tuple[int, int]] = {
    "U": (0, (1 << 64) - 1),
    "I": (-(1 << 63), (1 << 63) - 1),
    "usize": (0, (1 << 64) - 1),
    "isize": (-(1 << 63), (1 << 63) - 1),
    "u8": (0, (1 << 8) - 1),
    "i8": (-(1 << 7), (1 << 7) - 1),
    "u16": (0, (1 << 16) - 1),
    "i16": (-(1 << 15), (1 << 15) - 1),
    "u32": (0, (1 << 32) - 1),
    "i32": (-(1 << 31), (1 << 31) - 1),
    "u64": (0, (1 << 64) - 1),
    "i64": (-(1 << 63), (1 << 63) - 1),
    "u128": (0, (1 << 128) - 1),
    "i128": (-(1 << 127), (1 << 127) - 1),
}
_OPTION_NAMES = {"O", "Option"}
_RESULT_NAMES = {"R", "Result"}
_COMPARISONS = {"==", "=", "!=", "<", "<=", ">", ">="}


@dataclass(frozen=True)
class CoverageRegion:
    value: FiniteValue
    cardinality: int
    display: str

    @property
    def singleton(self) -> bool:
        return self.cardinality == 1


@dataclass(frozen=True)
class PartitionedCoverageCase(MachineCoverageCase):
    multiplicity: str = "1"
    regions: tuple[CoverageBinding, ...] = ()


@dataclass(frozen=True)
class PartitionedMachineCoverage(MachineCoverage):
    partitioned: bool = True
    region_count: int = 0
    concrete_case_count: str | None = None


@dataclass(frozen=True)
class _Constraint:
    path: tuple[str, ...]
    op: str
    literal_kind: str
    literal: int | bool | str


def _expr_path(expr: Expr) -> tuple[str, ...] | None:
    if isinstance(expr, NameExpr):
        return (expr.name,)
    if isinstance(expr, FieldExpr):
        base = _expr_path(expr.base)
        return None if base is None else (*base, expr.field)
    return None


def _literal(expr: Expr) -> tuple[str, int | bool | str] | None:
    if isinstance(expr, BoolExpr):
        return ("bool", expr.value)
    if isinstance(expr, NumberExpr) and "." not in expr.value:
        return ("integer", int(expr.value))
    if isinstance(expr, NameExpr):
        return ("variant", expr.name)
    return None


def _reverse_comparison(op: str) -> str:
    return {
        "<": ">",
        "<=": ">=",
        ">": "<",
        ">=": "<=",
    }.get(op, op)


def _walk(expr: Expr) -> Sequence[Expr]:
    output: list[Expr] = [expr]
    if isinstance(expr, UnaryExpr):
        output.extend(_walk(expr.expr))
    elif isinstance(expr, TryExpr):
        output.extend(_walk(expr.expr))
    elif isinstance(expr, BinaryExpr):
        output.extend(_walk(expr.left))
        output.extend(_walk(expr.right))
    elif isinstance(expr, CallExpr):
        output.extend(_walk(expr.callee))
        for argument in expr.args:
            output.extend(_walk(argument))
    elif isinstance(expr, FieldExpr):
        output.extend(_walk(expr.base))
    return output


def _constraints(
    clauses: Sequence[tuple[Expr | None, Expr, int, bool]],
    parameter_names: set[str],
) -> tuple[_Constraint, ...]:
    output: list[_Constraint] = []
    for condition, _, _, _ in clauses:
        if condition is None:
            continue
        for expr in _walk(condition):
            if not isinstance(expr, BinaryExpr) or expr.op not in _COMPARISONS:
                continue
            left_path = _expr_path(expr.left)
            right_path = _expr_path(expr.right)
            left_literal = (
                None
                if isinstance(expr.left, NameExpr)
                and expr.left.name in parameter_names
                else _literal(expr.left)
            )
            right_literal = (
                None
                if isinstance(expr.right, NameExpr)
                and expr.right.name in parameter_names
                else _literal(expr.right)
            )
            if (
                left_path is not None
                and left_path[0] in parameter_names
                and right_literal is not None
            ):
                output.append(
                    _Constraint(left_path, expr.op, right_literal[0], right_literal[1])
                )
            elif (
                right_path is not None
                and right_path[0] in parameter_names
                and left_literal is not None
            ):
                output.append(
                    _Constraint(
                        right_path,
                        _reverse_comparison(expr.op),
                        left_literal[0],
                        left_literal[1],
                    )
                )
    return tuple(output)


def _root_is_referenced(
    clauses: Sequence[tuple[Expr | None, Expr, int, bool]],
    roots: Sequence[str],
) -> bool:
    root_set = set(roots)
    for condition, _, _, _ in clauses:
        if condition is None:
            continue
        for expr in _walk(condition):
            path = _expr_path(expr)
            if path is not None and path[0] in root_set:
                return True
    return False


def _condition_partition_safe(expr: Expr, parameter_names: set[str]) -> bool:
    if isinstance(expr, BoolExpr):
        return True
    if isinstance(expr, (NameExpr, FieldExpr)):
        return True
    if isinstance(expr, UnaryExpr):
        return expr.op == "!" and _condition_partition_safe(expr.expr, parameter_names)
    if not isinstance(expr, BinaryExpr):
        return False
    if expr.op in {"&", "|"}:
        return _condition_partition_safe(
            expr.left, parameter_names
        ) and _condition_partition_safe(expr.right, parameter_names)
    if expr.op not in _COMPARISONS:
        return False
    left_path = _expr_path(expr.left)
    right_path = _expr_path(expr.right)
    left_literal = (
        None
        if isinstance(expr.left, NameExpr) and expr.left.name in parameter_names
        else _literal(expr.left)
    )
    right_literal = (
        None
        if isinstance(expr.right, NameExpr) and expr.right.name in parameter_names
        else _literal(expr.right)
    )
    return (
        left_path is not None
        and left_path[0] in parameter_names
        and right_literal is not None
    ) or (
        right_path is not None
        and right_path[0] in parameter_names
        and left_literal is not None
    )


class _PartitionDomain:
    def __init__(
        self,
        program: Program,
        constraints: Sequence[_Constraint],
        clauses: Sequence[tuple[Expr | None, Expr, int, bool]],
        *,
        partition_limit: int,
        materialization_limit: int,
    ) -> None:
        self.program = program
        self.constraints = tuple(constraints)
        self.clauses = tuple(clauses)
        self.partition_limit = partition_limit
        self.materialization_limit = materialization_limit
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
        self.finite = _FiniteDomain(program, materialization_limit)

    def resolve(self, ty: TypeRef) -> TypeRef:
        seen: set[str] = set()
        current = ty
        while (
            not current.args
            and current.name in self.aliases
            and current.name not in seen
        ):
            seen.add(current.name)
            current = self.aliases[current.name].target
        return current

    def cardinality(self, ty: TypeRef, stack: tuple[str, ...] = ()) -> int | None:
        resolved = self.resolve(ty)
        if resolved.name in _INTEGER_BOUNDS and not resolved.args:
            lower, upper = _INTEGER_BOUNDS[resolved.name]
            return upper - lower + 1
        if resolved.name in {"bool", "B"} and not resolved.args:
            return 2
        if resolved.name in {"()", "Unit"} and not resolved.args:
            return 1
        if resolved.name == "Never" and not resolved.args:
            return 0
        if resolved.name in stack:
            return None
        next_stack = (*stack, resolved.name)
        if not resolved.args and resolved.name in self.products:
            result = 1
            for field in self.products[resolved.name].fields:
                field_cardinality = self.cardinality(field.ty, next_stack)
                if field_cardinality is None:
                    return None
                result *= field_cardinality
            return result
        if not resolved.args and resolved.name in self.sums:
            result = 0
            for variant in self.sums[resolved.name].variants:
                payload = (
                    variant.tuple_types
                    if variant.tuple_types
                    else tuple(field.ty for field in variant.fields)
                )
                variant_cardinality = 1
                for item in payload:
                    item_cardinality = self.cardinality(item, next_stack)
                    if item_cardinality is None:
                        return None
                    variant_cardinality *= item_cardinality
                result += variant_cardinality
            return result
        if resolved.name == "tuple":
            result = 1
            for argument in resolved.args:
                item = self.cardinality(argument, next_stack)
                if item is None:
                    return None
                result *= item
            return result
        if resolved.name in _OPTION_NAMES and len(resolved.args) == 1:
            inner = self.cardinality(resolved.args[0], next_stack)
            return None if inner is None else inner + 1
        if resolved.name in _RESULT_NAMES and len(resolved.args) == 2:
            left = self.cardinality(resolved.args[0], next_stack)
            right = self.cardinality(resolved.args[1], next_stack)
            return None if left is None or right is None else left + right
        return None

    def representative(
        self,
        ty: TypeRef,
        stack: tuple[str, ...] = (),
    ) -> FiniteValue | None:
        resolved = self.resolve(ty)
        if resolved.name in _INTEGER_BOUNDS and not resolved.args:
            lower, _ = _INTEGER_BOUNDS[resolved.name]
            return FiniteValue(
                _render_type(resolved),
                "scalar",
                str(lower),
                scalar=lower,
            )
        if resolved.name in {"bool", "B"} and not resolved.args:
            return FiniteValue("bool", "scalar", "false", scalar=False)
        if resolved.name in {"()", "Unit"} and not resolved.args:
            return FiniteValue(resolved.name, "unit", "()")
        if resolved.name == "Never" and not resolved.args:
            return None
        if resolved.name in stack:
            return None
        next_stack = (*stack, resolved.name)
        if not resolved.args and resolved.name in self.products:
            declaration = self.products[resolved.name]
            fields: list[tuple[str, FiniteValue]] = []
            for field in declaration.fields:
                value = self.representative(field.ty, next_stack)
                if value is None:
                    return None
                fields.append((field.name, value))
            return FiniteValue(
                declaration.name,
                "product",
                f"{declaration.name} {{ "
                + ", ".join(f"{name}: {value.display}" for name, value in fields)
                + " }",
                fields=tuple(fields),
            )
        if not resolved.args and resolved.name in self.sums:
            declaration = self.sums[resolved.name]
            if not declaration.variants:
                return None
            return self._variant_representative(
                declaration,
                declaration.variants[0].name,
                next_stack,
            )
        values = self.finite.values_for_ref(resolved)
        return None if not values else values[0]

    def _variant_representative(
        self,
        declaration: SumDecl,
        variant_name: str,
        stack: tuple[str, ...] = (),
    ) -> FiniteValue | None:
        variant = next(
            (item for item in declaration.variants if item.name == variant_name),
            None,
        )
        if variant is None:
            return None
        payload = (
            variant.tuple_types
            if variant.tuple_types
            else tuple(field.ty for field in variant.fields)
        )
        values: list[FiniteValue] = []
        for item in payload:
            value = self.representative(item, (*stack, declaration.name))
            if value is None:
                return None
            values.append(value)
        if variant.tuple_types:
            fields = tuple((str(index), value) for index, value in enumerate(values))
            display = f"{declaration.name}::{variant.name}(" + ", ".join(
                value.display for value in values
            ) + ")"
        elif variant.fields:
            fields = tuple(
                (field.name, value)
                for field, value in zip(variant.fields, values)
            )
            display = f"{declaration.name}::{variant.name} {{ " + ", ".join(
                f"{field.name}: {value.display}"
                for field, value in zip(variant.fields, values)
            ) + " }"
        else:
            fields = ()
            display = f"{declaration.name}::{variant.name}"
        return FiniteValue(
            declaration.name,
            "variant",
            display,
            variant=variant.name,
            fields=fields,
        )

    def _paths(self, roots: Sequence[str], suffix: tuple[str, ...]) -> set[tuple[str, ...]]:
        return {tuple((root, *suffix)) for root in roots}

    def _referenced(
        self,
        roots: Sequence[str],
        suffix: tuple[str, ...],
    ) -> bool:
        paths = self._paths(roots, suffix)
        for condition, _, _, _ in self.clauses:
            if condition is None:
                continue
            for expr in _walk(condition):
                path = _expr_path(expr)
                if path is not None and (
                    path in paths
                    or any(path[: len(item)] == item for item in paths)
                    or any(item[: len(path)] == path for item in paths)
                ):
                    return True
        return False

    def _matching_constraints(
        self,
        roots: Sequence[str],
        suffix: tuple[str, ...],
    ) -> tuple[_Constraint, ...]:
        paths = self._paths(roots, suffix)
        return tuple(item for item in self.constraints if item.path in paths)

    def regions(
        self,
        ty: TypeRef,
        roots: Sequence[str],
        suffix: tuple[str, ...] = (),
    ) -> tuple[CoverageRegion, ...] | None:
        resolved = self.resolve(ty)
        cardinality = self.cardinality(resolved)
        if cardinality is None:
            return None
        referenced = self._referenced(roots, suffix)

        if resolved.name in _INTEGER_BOUNDS and not resolved.args:
            lower, upper = _INTEGER_BOUNDS[resolved.name]
            boundaries = {lower, upper + 1}
            for constraint in self._matching_constraints(roots, suffix):
                if constraint.literal_kind != "integer":
                    continue
                value = int(constraint.literal)
                if constraint.op in {"==", "=", "!="}:
                    boundaries.update((value, value + 1))
                elif constraint.op in {"<", ">="}:
                    boundaries.add(value)
                elif constraint.op in {"<=", ">"}:
                    boundaries.add(value + 1)
            ordered = sorted(
                value
                for value in boundaries
                if lower <= value <= upper + 1
            )
            regions: list[CoverageRegion] = []
            for start, stop in zip(ordered, ordered[1:]):
                if start >= stop:
                    continue
                end = stop - 1
                display = str(start) if start == end else f"{start}..={end}"
                regions.append(
                    CoverageRegion(
                        FiniteValue(
                            _render_type(resolved),
                            "scalar",
                            str(start),
                            scalar=start,
                        ),
                        end - start + 1,
                        display,
                    )
                )
            return tuple(regions)

        if resolved.name in {"bool", "B"} and not resolved.args:
            if not referenced:
                return (
                    CoverageRegion(
                        FiniteValue("bool", "scalar", "false", scalar=False),
                        2,
                        "false|true",
                    ),
                )
            return (
                CoverageRegion(
                    FiniteValue("bool", "scalar", "false", scalar=False),
                    1,
                    "false",
                ),
                CoverageRegion(
                    FiniteValue("bool", "scalar", "true", scalar=True),
                    1,
                    "true",
                ),
            )

        if resolved.name in {"()", "Unit"} and not resolved.args:
            value = FiniteValue(resolved.name, "unit", "()")
            return (CoverageRegion(value, 1, "()"),)

        if not resolved.args and resolved.name in self.products:
            declaration = self.products[resolved.name]
            factors: list[tuple[CoverageRegion, ...]] = []
            for field in declaration.fields:
                field_regions = self.regions(
                    field.ty,
                    roots,
                    (*suffix, field.name),
                )
                if field_regions is None:
                    return None
                factors.append(field_regions)
            region_count = 1
            for factor in factors:
                region_count *= len(factor)
                if region_count > self.partition_limit:
                    return None
            output: list[CoverageRegion] = []
            combinations = cartesian_product(*factors) if factors else ((),)
            for combination in combinations:
                fields = tuple(
                    (field.name, region.value)
                    for field, region in zip(declaration.fields, combination)
                )
                value = FiniteValue(
                    declaration.name,
                    "product",
                    f"{declaration.name} {{ "
                    + ", ".join(
                        f"{name}: {item.display}" for name, item in fields
                    )
                    + " }",
                    fields=fields,
                )
                weight = 1
                for region in combination:
                    weight *= region.cardinality
                display = (
                    f"{declaration.name} {{ "
                    + ", ".join(
                        f"{field.name}: {region.display}"
                        for field, region in zip(declaration.fields, combination)
                    )
                    + " }"
                )
                output.append(CoverageRegion(value, weight, display))
            return tuple(output)

        if not resolved.args and resolved.name in self.sums:
            declaration = self.sums[resolved.name]
            compared = {
                str(item.literal)
                for item in self._matching_constraints(roots, suffix)
                if item.literal_kind == "variant"
            }
            if not referenced:
                representative = self.representative(resolved)
                return (
                    None
                    if representative is None
                    else (CoverageRegion(representative, cardinality, "*"),)
                )
            output: list[CoverageRegion] = []
            remaining: list[tuple[FiniteValue, int]] = []
            for variant in declaration.variants:
                payload = (
                    variant.tuple_types
                    if variant.tuple_types
                    else tuple(field.ty for field in variant.fields)
                )
                payload_cardinality = 1
                for item in payload:
                    item_cardinality = self.cardinality(item)
                    if item_cardinality is None:
                        return None
                    payload_cardinality *= item_cardinality
                representative = self._variant_representative(
                    declaration,
                    variant.name,
                )
                if representative is None:
                    return None
                if variant.name in compared:
                    output.append(
                        CoverageRegion(
                            representative,
                            payload_cardinality,
                            representative.display
                            if payload_cardinality == 1
                            else f"{declaration.name}::{variant.name}(*)",
                        )
                    )
                else:
                    remaining.append((representative, payload_cardinality))
            if remaining:
                weight = sum(item[1] for item in remaining)
                output.append(
                    CoverageRegion(
                        remaining[0][0],
                        weight,
                        "{" + ", ".join(
                            item[0].variant or item[0].display for item in remaining
                        ) + "}",
                    )
                )
            return tuple(output)

        values = self.finite.values_for_ref(resolved)
        if values is not None:
            if referenced:
                return tuple(CoverageRegion(value, 1, value.display) for value in values)
            if not values:
                return ()
            return (CoverageRegion(values[0], len(values), "*"),)

        representative = self.representative(resolved)
        if representative is None:
            return None
        return (CoverageRegion(representative, cardinality, "*"),)


def _input_roots(
    machine: MachineDecl,
    next_decl: FunctionDecl,
    input_name: str,
) -> tuple[str, ...]:
    next_call = machine.next_expr
    if not isinstance(next_call, CallExpr):
        return ()
    roots = [
        parameter.name
        for parameter, argument in zip(next_decl.params, next_call.args)
        if isinstance(argument, NameExpr) and argument.name == input_name
    ]
    return tuple(roots)


def _unknown_partitioned(
    machine: MachineDecl,
    baseline: MachineCoverage,
    reason: str,
) -> MachineCoverage:
    return PartitionedMachineCoverage(
        machine=baseline.machine,
        state_type=baseline.state_type,
        input_types=baseline.input_types,
        state_cardinality=baseline.state_cardinality,
        input_cardinality=baseline.input_cardinality,
        possible_pairs=baseline.possible_pairs,
        defined_pairs=0,
        missing_pairs=None,
        complete=None,
        reason=reason,
        domain_semantics="selector×symbolic-input-partition",
        selector_field=baseline.selector_field,
        selector_type=baseline.selector_type,
        selector_cardinality=baseline.selector_cardinality,
        exact=False,
        partitioned=True,
        region_count=0,
        concrete_case_count=baseline.possible_pairs,
    )


def _build_partitioned_machine(
    program: Program,
    machine: MachineDecl,
    baseline: MachineCoverage,
    *,
    partition_limit: int,
    materialization_limit: int,
) -> MachineCoverage:
    parts = _machine_parts(program, machine)
    if parts is None:
        return baseline
    state_decl, selector_index, selector_field, selector_sum, next_decl = parts
    clauses = _clauses(next_decl)
    parameter_names = {item.name for item in next_decl.params}
    constraints = _constraints(clauses, parameter_names)
    domain = _PartitionDomain(
        program,
        constraints,
        clauses,
        partition_limit=partition_limit,
        materialization_limit=materialization_limit,
    )
    selector_values = _FiniteDomain(
        program,
        materialization_limit,
    ).values_for_name(selector_sum.name)
    if selector_values is None:
        return _unknown_partitioned(
            machine,
            baseline,
            "selector domain cannot be materialized for partitioned coverage",
        )

    input_regions: list[tuple[CoverageRegion, ...]] = []
    input_cardinality = 1
    for parameter in machine.input_params:
        roots = _input_roots(machine, next_decl, parameter.name)
        if not roots:
            return _unknown_partitioned(
                machine,
                baseline,
                f"machine input `{parameter.name}` is not passed directly to the next function",
            )
        cardinality = domain.cardinality(parameter.ty)
        regions = domain.regions(parameter.ty, roots)
        if cardinality is None or regions is None:
            return _unknown_partitioned(
                machine,
                baseline,
                f"input `{parameter.name}` cannot be partitioned exactly",
            )
        input_cardinality *= cardinality
        input_regions.append(regions)

    region_product = 1
    for regions in input_regions:
        region_product *= len(regions)
    total_regions = len(selector_values) * region_product
    if total_regions > partition_limit:
        return _unknown_partitioned(
            machine,
            baseline,
            f"symbolic selector×input partition has {total_regions} regions, "
            f"exceeding limit {partition_limit}",
        )

    possible = len(selector_values) * input_cardinality
    guard_true = [0] * len(clauses)
    guard_first = [0] * len(clauses)
    guard_shadowed = [0] * len(clauses)
    guard_unknown = [0] * len(clauses)
    cases: list[PartitionedCoverageCase] = []
    counts = {
        name: 0
        for name in ("defined", "rejected", "fallthrough", "missing", "unknown")
    }
    overlap_pairs = 0
    input_combinations = (
        tuple(cartesian_product(*input_regions)) if input_regions else ((),)
    )

    for selector_value in selector_values:
        for combination in input_combinations:
            weight = 1
            for region in combination:
                weight *= region.cardinality
            representative_inputs = {
                parameter.name: region.value
                for parameter, region in zip(machine.input_params, combination)
            }
            environment = _function_environment(
                machine,
                next_decl,
                selector_field,
                selector_value,
                representative_inputs,
            )
            symbolic = any(not region.singleton for region in combination)
            evaluations: list[bool | None] = []
            explicit_true: list[int] = []
            for index, (condition, _, _, is_default) in enumerate(clauses):
                if condition is None:
                    evaluations.append(True if not is_default else None)
                    continue
                truth = (
                    _truth(_eval_expr(condition, environment))
                    if not symbolic
                    or _condition_partition_safe(condition, parameter_names)
                    else None
                )
                evaluations.append(truth)
                if truth is True:
                    explicit_true.append(index + 1)
                    guard_true[index] += weight
                elif truth is None:
                    guard_unknown[index] += weight
            if len(explicit_true) > 1:
                overlap_pairs += weight

            selected: int | None = None
            selection_unknown = False
            unknown_seen = False
            for index, (
                (condition, _, _, is_default),
                truth,
            ) in enumerate(zip(clauses, evaluations)):
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
                reason = "ordered branch selection is not uniform over the symbolic region"
            elif selected is None:
                outcome = "missing"
                reason = "no guard matched and no default clause exists"
            else:
                _, value, line, is_default = clauses[selected]
                guard_first[selected] += weight
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
            counts[outcome] += weight
            cases.append(
                PartitionedCoverageCase(
                    index=len(cases),
                    selector=selector_value.display,
                    inputs=tuple(
                        CoverageBinding(parameter.name, region.value.display)
                        for parameter, region in zip(
                            machine.input_params,
                            combination,
                        )
                    ),
                    outcome=outcome,
                    selected_clause=None if selected is None else selected + 1,
                    matching_clauses=tuple(explicit_true),
                    target_state=target_state,
                    line=line,
                    reason=reason,
                    multiplicity=str(weight),
                    regions=tuple(
                        CoverageBinding(parameter.name, region.display)
                        for parameter, region in zip(
                            machine.input_params,
                            combination,
                        )
                    ),
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
                condition=(
                    "otherwise"
                    if is_default
                    else "always"
                    if condition is None
                    else render_expr(condition)
                ),
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
    return PartitionedMachineCoverage(
        machine=machine.name,
        state_type=state_decl.name,
        input_types=tuple(_render_type(item.ty) for item in machine.input_params),
        state_cardinality=str(len(selector_values)),
        input_cardinality=str(input_cardinality),
        possible_pairs=str(possible),
        defined_pairs=counts["defined"],
        missing_pairs=str(missing),
        complete=missing == 0 and unknown == 0,
        reason=None,
        domain_semantics="selector×symbolic-input-partition",
        selector_field=selector_field,
        selector_type=selector_sum.name,
        selector_cardinality=str(len(selector_values)),
        rejected_pairs=counts["rejected"],
        fallthrough_pairs=counts["fallthrough"],
        overlap_pairs=overlap_pairs,
        unknown_pairs=unknown,
        exact=unknown == 0,
        cases=tuple(cases),
        guards=tuple(guard_rows),
        partitioned=True,
        region_count=len(cases),
        concrete_case_count=str(possible),
    )


def build_machine_coverage(
    program: Program,
    machines: Sequence[MachineDecl],
    execution_ir: ExecutionStructureIR,
    algebra: object,
    *,
    coverage_limit: int = _DEFAULT_PARTITION_LIMIT,
    partition_limit: int | None = None,
    materialization_limit: int = _DEFAULT_MATERIALIZATION_LIMIT,
) -> tuple[MachineCoverage, ...]:
    """Use exact enumeration when small, then guard-driven symbolic partitions."""

    effective_partition_limit = (
        coverage_limit if partition_limit is None else partition_limit
    )
    if effective_partition_limit < 1:
        raise ValueError("partition_limit must be positive")
    if materialization_limit < effective_partition_limit:
        materialization_limit = effective_partition_limit

    baseline = _build_enumerated_coverage(
        program,
        machines,
        execution_ir,
        algebra,
        coverage_limit=coverage_limit,
    )
    by_name = {item.name: item for item in machines}
    output: list[MachineCoverage] = []
    for row in baseline:
        if row.exact:
            output.append(row)
            continue
        machine = by_name.get(row.machine)
        if machine is None:
            output.append(row)
            continue
        output.append(
            _build_partitioned_machine(
                program,
                machine,
                row,
                partition_limit=effective_partition_limit,
                materialization_limit=materialization_limit,
            )
        )
    return tuple(output)

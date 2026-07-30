from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, TypeAlias

from ..artifacts import CompilationModel
from ..compiler import (
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
    SumDecl,
    TryExpr,
    TypeRef,
    UnaryExpr,
)
from .concrete import ConstructorValue, VariantValue
from .finite_domain import FiniteDomainError, finite_assignments


TYPED_SMT_ENCODING_VERSION = 1


class SolverOutcome(str, Enum):
    UNSAT_PROVEN = "unsat-proven"
    SAT_MODEL = "sat-model"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class UnsatProven:
    certificate: str
    outcome: SolverOutcome = SolverOutcome.UNSAT_PROVEN

    def to_ir(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "certificate": self.certificate,
        }


@dataclass(frozen=True)
class SatModel:
    assignments: tuple[tuple[str, object], ...]
    outcome: SolverOutcome = SolverOutcome.SAT_MODEL

    @property
    def mapping(self) -> dict[str, object]:
        return dict(self.assignments)

    def to_ir(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "assignments": {
                name: repr(value) for name, value in self.assignments
            },
        }


@dataclass(frozen=True)
class SolverUnknown:
    reason: str
    outcome: SolverOutcome = SolverOutcome.UNKNOWN

    def to_ir(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
        }


SolverResult: TypeAlias = UnsatProven | SatModel | SolverUnknown


@dataclass(frozen=True)
class EncodedPredicate:
    expression: Expr
    variables: tuple[tuple[str, TypeRef], ...]
    result_type: TypeRef
    encoding_version: int = TYPED_SMT_ENCODING_VERSION

    def to_ir(self) -> dict[str, object]:
        return {
            "encoding_version": self.encoding_version,
            "expression": repr(self.expression),
            "variables": [
                {"name": name, "type": _render_type(type_ref)}
                for name, type_ref in self.variables
            ],
            "result_type": _render_type(self.result_type),
        }


class TypedEncodingError(ValueError):
    pass


class TypedEvaluationError(ValueError):
    pass


class TypedPredicateEncoder:
    """Validate a Glyph predicate against explicit variable types.

    This module is the solver trust boundary.  An expression is never sent to a
    backend as an untyped string: field access, constructors, variants, function
    calls and operators are checked against the compiler model first.
    """

    def __init__(self, model: CompilationModel) -> None:
        self.model = model
        self.aliases = {
            declaration.name: declaration.target
            for declaration in model.program.declarations
            if isinstance(declaration, AliasDecl)
        }
        self.products = {
            declaration.name: declaration
            for declaration in model.program.declarations
            if isinstance(declaration, ProductDecl)
        }
        self.sums = {
            declaration.name: declaration
            for declaration in model.program.declarations
            if isinstance(declaration, SumDecl)
        }
        self.variants = {
            variant.name: (declaration, variant)
            for declaration in self.sums.values()
            for variant in declaration.variants
        }
        self.functions = {
            declaration.name: declaration
            for declaration in model.program.declarations
            if isinstance(declaration, FunctionDecl)
        }

    def encode(
        self,
        expression: Expr,
        type_environment: Mapping[str, TypeRef],
    ) -> EncodedPredicate:
        used: set[str] = set()
        result_type = self._infer(expression, type_environment, used)
        if not _is_bool(self._resolve(result_type)):
            raise TypedEncodingError(
                f"solver predicate must be Boolean, got {_render_type(result_type)}"
            )
        variables = tuple(
            sorted(
                (
                    (name, self._resolve(type_environment[name]))
                    for name in used
                ),
                key=lambda item: item[0],
            )
        )
        return EncodedPredicate(expression, variables, self._resolve(result_type))

    def _resolve(self, type_ref: TypeRef) -> TypeRef:
        seen: set[str] = set()
        current = type_ref
        while current.name in self.aliases and current.name not in seen:
            seen.add(current.name)
            current = self.aliases[current.name]
        if current.args:
            return TypeRef(
                current.name,
                tuple(self._resolve(argument) for argument in current.args),
            )
        return current

    def _infer(
        self,
        expression: Expr,
        environment: Mapping[str, TypeRef],
        used: set[str],
    ) -> TypeRef:
        if isinstance(expression, BoolExpr):
            return TypeRef("B")
        if isinstance(expression, NumberExpr):
            return TypeRef("F" if "." in expression.value else "I")
        if isinstance(expression, NameExpr):
            if expression.name in environment:
                used.add(expression.name)
                return self._resolve(environment[expression.name])
            variant = self.variants.get(expression.name)
            if variant is not None:
                declaration, item = variant
                if item.fields or item.tuple_types:
                    raise TypedEncodingError(
                        f"variant {expression.name} requires constructor arguments"
                    )
                return TypeRef(declaration.name)
            raise TypedEncodingError(f"untyped solver name {expression.name}")
        if isinstance(expression, FieldExpr):
            base_type = self._resolve(self._infer(expression.base, environment, used))
            product = self.products.get(base_type.name)
            if product is None:
                raise TypedEncodingError(
                    f"field access {expression.field} requires product type, got "
                    f"{_render_type(base_type)}"
                )
            field = next(
                (item for item in product.fields if item.name == expression.field),
                None,
            )
            if field is None:
                raise TypedEncodingError(
                    f"product {product.name} has no field {expression.field}"
                )
            return self._resolve(field.ty)
        if isinstance(expression, TryExpr):
            raise TypedEncodingError("try expressions are not predicate terms")
        if isinstance(expression, UnaryExpr):
            operand = self._resolve(self._infer(expression.expr, environment, used))
            if expression.op == "!":
                if not _is_bool(operand):
                    raise TypedEncodingError("! requires a Boolean operand")
                return TypeRef("B")
            if expression.op == "-":
                if not _is_numeric(operand):
                    raise TypedEncodingError("unary - requires a numeric operand")
                return operand
            raise TypedEncodingError(f"unsupported unary operator {expression.op}")
        if isinstance(expression, BinaryExpr):
            left = self._resolve(self._infer(expression.left, environment, used))
            right = self._resolve(self._infer(expression.right, environment, used))
            if expression.op in {"&", "|"}:
                if not _is_bool(left) or not _is_bool(right):
                    raise TypedEncodingError(
                        f"{expression.op} requires Boolean operands"
                    )
                return TypeRef("B")
            if expression.op in {"==", "!="}:
                if not _compatible(left, right):
                    raise TypedEncodingError(
                        "equality operands have incompatible types: "
                        f"{_render_type(left)} and {_render_type(right)}"
                    )
                return TypeRef("B")
            if expression.op in {"<", "<=", ">", ">="}:
                if not _is_numeric(left) or not _compatible(left, right):
                    raise TypedEncodingError(
                        f"{expression.op} requires compatible numeric operands"
                    )
                return TypeRef("B")
            if expression.op in {"+", "-", "*", "/"}:
                if not _is_numeric(left) or not _compatible(left, right):
                    raise TypedEncodingError(
                        f"{expression.op} requires compatible numeric operands"
                    )
                return left
            raise TypedEncodingError(f"unsupported binary operator {expression.op}")
        if isinstance(expression, CallExpr):
            if not isinstance(expression.callee, NameExpr):
                raise TypedEncodingError("solver supports named calls only")
            name = expression.callee.name
            argument_types = tuple(
                self._resolve(self._infer(argument, environment, used))
                for argument in expression.args
            )
            product = self.products.get(name)
            if product is not None:
                expected = tuple(self._resolve(field.ty) for field in product.fields)
                _check_arguments(name, argument_types, expected)
                return TypeRef(name)
            variant = self.variants.get(name)
            if variant is not None:
                declaration, item = variant
                expected = tuple(
                    self._resolve(field.ty) for field in item.fields
                ) if item.fields else tuple(
                    self._resolve(type_ref) for type_ref in item.tuple_types
                )
                _check_arguments(name, argument_types, expected)
                return TypeRef(declaration.name)
            if name in {"min", "max"}:
                if len(argument_types) != 2:
                    raise TypedEncodingError(f"{name} expects two arguments")
                if not _is_numeric(argument_types[0]) or not _compatible(
                    argument_types[0], argument_types[1]
                ):
                    raise TypedEncodingError(
                        f"{name} requires compatible numeric arguments"
                    )
                return argument_types[0]
            function = self.functions.get(name)
            if function is None:
                raise TypedEncodingError(f"unknown solver call target {name}")
            expected = tuple(self._resolve(parameter.ty) for parameter in function.params)
            _check_arguments(name, argument_types, expected)
            return self._resolve(function.return_type)
        raise TypedEncodingError(f"unsupported predicate expression {expression!r}")


class TypedConstraintSolver:
    """Three-valued typed solver with an exact finite-domain backend.

    The backend proves UNSAT only after exhaustive enumeration of all values of
    every typed free variable.  A satisfying assignment is returned as a concrete
    model.  Unbounded, recursive, unsupported or over-budget domains return
    ``SolverUnknown`` and can never be interpreted as UNSAT.
    """

    def __init__(
        self,
        model: CompilationModel,
        *,
        max_assignments: int = 4096,
        max_call_depth: int = 64,
    ) -> None:
        self.model = model
        self.encoder = TypedPredicateEncoder(model)
        self.max_assignments = max_assignments
        self.max_call_depth = max_call_depth
        self.products = self.encoder.products
        self.variants = self.encoder.variants
        self.functions = self.encoder.functions

    def solve(
        self,
        expression: Expr,
        type_environment: Mapping[str, TypeRef],
    ) -> SolverResult:
        try:
            encoded = self.encoder.encode(expression, type_environment)
            assignments = finite_assignments(
                self.model,
                encoded.variables,
                max_cases=self.max_assignments,
            )
        except (TypedEncodingError, FiniteDomainError) as error:
            return SolverUnknown(str(error))

        try:
            for assignment in assignments:
                value = self._evaluate(
                    encoded.expression,
                    assignment,
                    depth=0,
                    call_stack=(),
                )
                if not isinstance(value, bool):
                    return SolverUnknown(
                        f"encoded predicate evaluated to non-Boolean {value!r}"
                    )
                if value:
                    return SatModel(
                        tuple(sorted(assignment.items(), key=lambda item: item[0]))
                    )
        except TypedEvaluationError as error:
            return SolverUnknown(str(error))

        return UnsatProven(
            "exhaustive typed finite-domain enumeration "
            f"({len(assignments)} assignments)"
        )

    def _evaluate(
        self,
        expression: Expr,
        environment: Mapping[str, object],
        *,
        depth: int,
        call_stack: tuple[str, ...],
    ) -> object:
        if depth > self.max_call_depth:
            raise TypedEvaluationError("typed solver call-depth limit exceeded")
        if isinstance(expression, BoolExpr):
            return expression.value
        if isinstance(expression, NumberExpr):
            return float(expression.value) if "." in expression.value else int(expression.value)
        if isinstance(expression, NameExpr):
            if expression.name in environment:
                return environment[expression.name]
            variant = self.variants.get(expression.name)
            if variant is not None:
                _, item = variant
                if item.fields or item.tuple_types:
                    raise TypedEvaluationError(
                        f"variant {expression.name} requires arguments"
                    )
                return VariantValue(expression.name)
            raise TypedEvaluationError(f"unbound typed solver name {expression.name}")
        if isinstance(expression, FieldExpr):
            base = self._evaluate(
                expression.base,
                environment,
                depth=depth,
                call_stack=call_stack,
            )
            if not isinstance(base, ConstructorValue):
                raise TypedEvaluationError(
                    f"field access {expression.field} requires a constructor"
                )
            return base.field(expression.field)
        if isinstance(expression, TryExpr):
            raise TypedEvaluationError("try expressions are not predicate terms")
        if isinstance(expression, UnaryExpr):
            value = self._evaluate(
                expression.expr,
                environment,
                depth=depth,
                call_stack=call_stack,
            )
            if expression.op == "!":
                if not isinstance(value, bool):
                    raise TypedEvaluationError("! requires Boolean value")
                return not value
            if expression.op == "-":
                return -value  # type: ignore[operator]
            raise TypedEvaluationError(f"unsupported unary operator {expression.op}")
        if isinstance(expression, BinaryExpr):
            left = self._evaluate(
                expression.left,
                environment,
                depth=depth,
                call_stack=call_stack,
            )
            if expression.op == "&":
                if not isinstance(left, bool):
                    raise TypedEvaluationError("& requires Boolean values")
                return left and bool(
                    self._evaluate(
                        expression.right,
                        environment,
                        depth=depth,
                        call_stack=call_stack,
                    )
                )
            if expression.op == "|":
                if not isinstance(left, bool):
                    raise TypedEvaluationError("| requires Boolean values")
                return left or bool(
                    self._evaluate(
                        expression.right,
                        environment,
                        depth=depth,
                        call_stack=call_stack,
                    )
                )
            right = self._evaluate(
                expression.right,
                environment,
                depth=depth,
                call_stack=call_stack,
            )
            operations = {
                "==": lambda a, b: a == b,
                "!=": lambda a, b: a != b,
                "+": lambda a, b: a + b,  # type: ignore[operator]
                "-": lambda a, b: a - b,  # type: ignore[operator]
                "*": lambda a, b: a * b,  # type: ignore[operator]
                "/": lambda a, b: a / b,  # type: ignore[operator]
                "<": lambda a, b: a < b,  # type: ignore[operator]
                "<=": lambda a, b: a <= b,  # type: ignore[operator]
                ">": lambda a, b: a > b,  # type: ignore[operator]
                ">=": lambda a, b: a >= b,  # type: ignore[operator]
            }
            operation = operations.get(expression.op)
            if operation is None:
                raise TypedEvaluationError(
                    f"unsupported binary operator {expression.op}"
                )
            return operation(left, right)
        if isinstance(expression, CallExpr):
            if not isinstance(expression.callee, NameExpr):
                raise TypedEvaluationError("typed solver supports named calls only")
            name = expression.callee.name
            arguments = tuple(
                self._evaluate(
                    argument,
                    environment,
                    depth=depth,
                    call_stack=call_stack,
                )
                for argument in expression.args
            )
            product = self.products.get(name)
            if product is not None:
                return ConstructorValue(
                    name,
                    tuple(
                        (field.name, value)
                        for field, value in zip(
                            product.fields,
                            arguments,
                            strict=True,
                        )
                    ),
                )
            if name in self.variants:
                return VariantValue(name, arguments)
            if name == "min":
                return min(arguments)
            if name == "max":
                return max(arguments)
            function = self.functions.get(name)
            if function is None:
                raise TypedEvaluationError(f"unknown call target {name}")
            if name in call_stack:
                raise TypedEvaluationError(
                    f"recursive predicate helper requires summary: {name}"
                )
            local = {
                parameter.name: value
                for parameter, value in zip(
                    function.params,
                    arguments,
                    strict=True,
                )
            }
            next_stack = (*call_stack, name)
            if function.expression is not None:
                return self._evaluate(
                    function.expression,
                    local,
                    depth=depth + 1,
                    call_stack=next_stack,
                )
            for clause in function.guards:
                if clause.condition is None:
                    return self._evaluate(
                        clause.value,
                        local,
                        depth=depth + 1,
                        call_stack=next_stack,
                    )
                selected = self._evaluate(
                    clause.condition,
                    local,
                    depth=depth + 1,
                    call_stack=next_stack,
                )
                if not isinstance(selected, bool):
                    raise TypedEvaluationError(
                        f"guarded helper {name} produced non-Boolean guard"
                    )
                if selected:
                    return self._evaluate(
                        clause.value,
                        local,
                        depth=depth + 1,
                        call_stack=next_stack,
                    )
            raise TypedEvaluationError(f"guarded helper {name} has no matching clause")
        raise TypedEvaluationError(f"unsupported expression {expression!r}")


def _check_arguments(
    name: str,
    actual: tuple[TypeRef, ...],
    expected: tuple[TypeRef, ...],
) -> None:
    if len(actual) != len(expected):
        raise TypedEncodingError(
            f"{name} expects {len(expected)} arguments, got {len(actual)}"
        )
    for index, (left, right) in enumerate(zip(actual, expected, strict=True)):
        if not _compatible(left, right):
            raise TypedEncodingError(
                f"argument {index + 1} of {name} has type {_render_type(left)}, "
                f"expected {_render_type(right)}"
            )


def _compatible(left: TypeRef, right: TypeRef) -> bool:
    return left == right or (_is_numeric(left) and _is_numeric(right))


def _is_bool(type_ref: TypeRef) -> bool:
    return type_ref.name in {"B", "bool"} and not type_ref.args


def _is_numeric(type_ref: TypeRef) -> bool:
    return type_ref.name in {
        "I",
        "F",
        "i8",
        "i16",
        "i32",
        "i64",
        "u8",
        "u16",
        "u32",
        "u64",
        "f32",
        "f64",
    } and not type_ref.args


def _render_type(type_ref: TypeRef) -> str:
    if not type_ref.args:
        return type_ref.name
    return f"{type_ref.name}<{','.join(_render_type(item) for item in type_ref.args)}>"

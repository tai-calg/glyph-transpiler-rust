from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, TypeAlias

from ..compiler import (
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    FieldExpr,
    NameExpr,
    NumberExpr,
    TryExpr,
    UnaryExpr,
)


@dataclass(frozen=True)
class BottomValue:
    pass


@dataclass(frozen=True)
class ParameterValue:
    context: str
    name: str


@dataclass(frozen=True)
class ConstantValue:
    value: object


@dataclass(frozen=True)
class FieldValue:
    base: "AbstractValue"
    field: str


@dataclass(frozen=True)
class ConstructorValue:
    type_name: str
    field_names: tuple[str, ...]
    arguments: tuple["AbstractValue", ...]

    def __post_init__(self) -> None:
        if len(self.field_names) != len(self.arguments):
            raise ValueError(
                f"constructor {self.type_name} has {len(self.field_names)} fields "
                f"but {len(self.arguments)} arguments"
            )


@dataclass(frozen=True)
class ApplicationValue:
    operation: str
    arguments: tuple["AbstractValue", ...]


@dataclass(frozen=True)
class PhiValue:
    values: tuple["AbstractValue", ...]


@dataclass(frozen=True)
class TopValue:
    reason: str


AbstractValue: TypeAlias = (
    BottomValue
    | ParameterValue
    | ConstantValue
    | FieldValue
    | ConstructorValue
    | ApplicationValue
    | PhiValue
    | TopValue
)


def normalize_value(value: AbstractValue) -> AbstractValue:
    if isinstance(value, FieldValue):
        base = normalize_value(value.base)
        if isinstance(base, ConstructorValue) and value.field in base.field_names:
            index = base.field_names.index(value.field)
            return normalize_value(base.arguments[index])
        return FieldValue(base, value.field)
    if isinstance(value, ConstructorValue):
        return ConstructorValue(
            value.type_name,
            value.field_names,
            tuple(normalize_value(argument) for argument in value.arguments),
        )
    if isinstance(value, ApplicationValue):
        arguments = tuple(normalize_value(argument) for argument in value.arguments)
        if value.operation == "identity" and len(arguments) == 1:
            return arguments[0]
        return ApplicationValue(value.operation, arguments)
    if isinstance(value, PhiValue):
        flattened: list[AbstractValue] = []
        for item in value.values:
            normalized = normalize_value(item)
            if isinstance(normalized, PhiValue):
                flattened.extend(normalized.values)
            elif not isinstance(normalized, BottomValue):
                flattened.append(normalized)
        unique: list[AbstractValue] = []
        for item in flattened:
            if not any(item == existing for existing in unique):
                unique.append(item)
        if not unique:
            return BottomValue()
        if len(unique) == 1:
            return unique[0]
        return PhiValue(tuple(unique))
    return value


def join_values(
    left: AbstractValue,
    right: AbstractValue,
    *,
    max_phi_values: int = 32,
) -> AbstractValue:
    left = normalize_value(left)
    right = normalize_value(right)
    if left == right:
        return left
    if isinstance(left, BottomValue):
        return right
    if isinstance(right, BottomValue):
        return left
    if isinstance(left, TopValue):
        return left
    if isinstance(right, TopValue):
        return right
    values = normalize_value(PhiValue((left, right)))
    if isinstance(values, PhiValue) and len(values.values) > max_phi_values:
        return TopValue("phi-budget")
    return values


def substitute_value(
    value: AbstractValue,
    parameters: Mapping[str, AbstractValue],
) -> AbstractValue:
    if isinstance(value, ParameterValue):
        return parameters.get(value.name, value)
    if isinstance(value, FieldValue):
        return normalize_value(
            FieldValue(substitute_value(value.base, parameters), value.field)
        )
    if isinstance(value, ConstructorValue):
        return normalize_value(
            ConstructorValue(
                value.type_name,
                value.field_names,
                tuple(substitute_value(argument, parameters) for argument in value.arguments),
            )
        )
    if isinstance(value, ApplicationValue):
        return normalize_value(
            ApplicationValue(
                value.operation,
                tuple(substitute_value(argument, parameters) for argument in value.arguments),
            )
        )
    if isinstance(value, PhiValue):
        return normalize_value(
            PhiValue(tuple(substitute_value(item, parameters) for item in value.values))
        )
    return value


def value_from_expr(
    expression: Expr,
    environment: Mapping[str, AbstractValue],
    *,
    context: str,
    product_fields: Mapping[str, tuple[str, ...]] | None = None,
    constants: frozenset[str] = frozenset(),
) -> AbstractValue:
    """Convert one Glyph expression to a structure-preserving abstract value."""

    product_fields = product_fields or {}
    if isinstance(expression, BoolExpr):
        return ConstantValue(expression.value)
    if isinstance(expression, NumberExpr):
        value: object = (
            float(expression.value) if "." in expression.value else int(expression.value)
        )
        return ConstantValue(value)
    if isinstance(expression, NameExpr):
        if expression.name in environment:
            return environment[expression.name]
        if expression.name in constants:
            return ConstantValue(expression.name)
        return ParameterValue(context, expression.name)
    if isinstance(expression, FieldExpr):
        return normalize_value(
            FieldValue(
                value_from_expr(
                    expression.base,
                    environment,
                    context=context,
                    product_fields=product_fields,
                    constants=constants,
                ),
                expression.field,
            )
        )
    if isinstance(expression, UnaryExpr):
        return ApplicationValue(
            expression.op,
            (
                value_from_expr(
                    expression.expr,
                    environment,
                    context=context,
                    product_fields=product_fields,
                    constants=constants,
                ),
            ),
        )
    if isinstance(expression, BinaryExpr):
        return ApplicationValue(
            expression.op,
            (
                value_from_expr(
                    expression.left,
                    environment,
                    context=context,
                    product_fields=product_fields,
                    constants=constants,
                ),
                value_from_expr(
                    expression.right,
                    environment,
                    context=context,
                    product_fields=product_fields,
                    constants=constants,
                ),
            ),
        )
    if isinstance(expression, TryExpr):
        return ApplicationValue(
            "try",
            (
                value_from_expr(
                    expression.expr,
                    environment,
                    context=context,
                    product_fields=product_fields,
                    constants=constants,
                ),
            ),
        )
    if isinstance(expression, CallExpr) and isinstance(expression.callee, NameExpr):
        arguments = tuple(
            value_from_expr(
                argument,
                environment,
                context=context,
                product_fields=product_fields,
                constants=constants,
            )
            for argument in expression.args
        )
        fields = product_fields.get(expression.callee.name)
        if fields is not None:
            return normalize_value(
                ConstructorValue(expression.callee.name, fields, arguments)
            )
        return ApplicationValue(expression.callee.name, arguments)
    return TopValue("unsupported-expression")

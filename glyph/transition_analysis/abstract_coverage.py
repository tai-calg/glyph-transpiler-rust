from __future__ import annotations

from typing import Mapping

from .abstract_state import GuardedAlternative
from .abstract_value import (
    AbstractValue,
    ApplicationValue,
    BottomValue,
    ConstantValue,
    ConstructorValue as AbstractConstructorValue,
    FieldValue,
    ParameterValue,
    PhiValue,
    TopValue,
)
from .concrete import ConstructorValue, ResultValue, VariantValue


_UNKNOWN_CONCRETE = object()


def abstract_value_covers(
    value: AbstractValue | None,
    concrete: object,
    inputs: Mapping[str, object],
    *,
    input_context: str | None = None,
) -> bool:
    if value is None:
        return concrete is None
    if isinstance(value, TopValue):
        return True
    if isinstance(value, BottomValue):
        return False
    if isinstance(value, ConstantValue):
        return value.value == concrete
    if isinstance(value, ParameterValue):
        if input_context is not None and value.context == input_context and value.name in inputs:
            return inputs[value.name] == concrete
        # A parameter from an instantiated helper/effect summary is an abstract
        # symbolic value unless its call context is explicitly tied to entry input.
        return True
    if isinstance(value, PhiValue):
        return any(
            abstract_value_covers(
                item,
                concrete,
                inputs,
                input_context=input_context,
            )
            for item in value.values
        )
    if isinstance(value, FieldValue):
        base = concrete_from_abstract(value.base, inputs, input_context=input_context)
        if isinstance(base, ConstructorValue):
            try:
                return base.field(value.field) == concrete
            except Exception:
                return False
        return base is _UNKNOWN_CONCRETE
    if isinstance(value, AbstractConstructorValue):
        if isinstance(concrete, ConstructorValue):
            if value.type_name != concrete.type_name:
                return False
            concrete_fields = dict(concrete.fields)
            return all(
                field_name in concrete_fields
                and abstract_value_covers(
                    argument,
                    concrete_fields[field_name],
                    inputs,
                    input_context=input_context,
                )
                for field_name, argument in zip(
                    value.field_names,
                    value.arguments,
                    strict=True,
                )
            )
        if isinstance(concrete, VariantValue):
            return (
                value.type_name == concrete.name
                and len(value.arguments) == len(concrete.arguments)
                and all(
                    abstract_value_covers(
                        argument,
                        item,
                        inputs,
                        input_context=input_context,
                    )
                    for argument, item in zip(
                        value.arguments,
                        concrete.arguments,
                        strict=True,
                    )
                )
            )
        return False
    if isinstance(value, ApplicationValue):
        evaluated = concrete_from_abstract(
            value,
            inputs,
            input_context=input_context,
        )
        return evaluated is _UNKNOWN_CONCRETE or evaluated == concrete
    return True


def abstract_store_covers(
    alternative: GuardedAlternative,
    concrete_store: object,
    inputs: Mapping[str, object],
    *,
    input_context: str | None = None,
) -> bool:
    if concrete_store in (None, (), {}):
        return True
    if isinstance(concrete_store, Mapping):
        items = tuple(concrete_store.items())
    elif isinstance(concrete_store, tuple):
        items = concrete_store
    else:
        return alternative.store.approximation.kind.value == "unknown"

    abstract = {
        (location.kind, location.key): value
        for location, value in alternative.store.bindings
    }
    for raw_location, concrete_value in items:
        if isinstance(raw_location, tuple) and len(raw_location) == 2:
            key = (str(raw_location[0]), str(raw_location[1]))
        else:
            key = ("external", str(raw_location))
        value = abstract.get(key)
        if value is None:
            if alternative.store.approximation.kind.value == "unknown":
                continue
            return False
        if not abstract_value_covers(
            value,
            concrete_value,
            inputs,
            input_context=input_context,
        ):
            return False
    return True


def concrete_from_abstract(
    value: AbstractValue,
    inputs: Mapping[str, object],
    *,
    input_context: str | None = None,
) -> object:
    if isinstance(value, ConstantValue):
        return value.value
    if isinstance(value, ParameterValue):
        if input_context is not None and value.context == input_context:
            return inputs.get(value.name, _UNKNOWN_CONCRETE)
        return _UNKNOWN_CONCRETE
    if isinstance(value, FieldValue):
        base = concrete_from_abstract(value.base, inputs, input_context=input_context)
        if isinstance(base, ConstructorValue):
            try:
                return base.field(value.field)
            except Exception:
                return _UNKNOWN_CONCRETE
        return _UNKNOWN_CONCRETE
    if isinstance(value, AbstractConstructorValue):
        arguments = tuple(
            concrete_from_abstract(
                argument,
                inputs,
                input_context=input_context,
            )
            for argument in value.arguments
        )
        if any(item is _UNKNOWN_CONCRETE for item in arguments):
            return _UNKNOWN_CONCRETE
        if value.field_names:
            return ConstructorValue(
                value.type_name,
                tuple(zip(value.field_names, arguments, strict=True)),
            )
        return VariantValue(value.type_name, arguments)
    if isinstance(value, ApplicationValue):
        arguments = tuple(
            concrete_from_abstract(
                argument,
                inputs,
                input_context=input_context,
            )
            for argument in value.arguments
        )
        if any(item is _UNKNOWN_CONCRETE for item in arguments):
            return _UNKNOWN_CONCRETE
        if value.operation in {"Ok", "Err"} and len(arguments) == 1:
            return ResultValue(value.operation == "Ok", arguments[0])
        operation = value.operation
        if operation == "-" and len(arguments) == 2:
            operation = "-binary"
        functions = {
            "!": lambda a: not a,
            "-": lambda a: -a,  # type: ignore[operator]
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "+": lambda a, b: a + b,  # type: ignore[operator]
            "-binary": lambda a, b: a - b,  # type: ignore[operator]
            "*": lambda a, b: a * b,  # type: ignore[operator]
            "/": lambda a, b: a / b,  # type: ignore[operator]
            "&": lambda a, b: bool(a) and bool(b),
            "|": lambda a, b: bool(a) or bool(b),
            "<": lambda a, b: a < b,  # type: ignore[operator]
            "<=": lambda a, b: a <= b,  # type: ignore[operator]
            ">": lambda a, b: a > b,  # type: ignore[operator]
            ">=": lambda a, b: a >= b,  # type: ignore[operator]
        }
        function = functions.get(operation)
        if function is None:
            return _UNKNOWN_CONCRETE
        try:
            return function(*arguments)
        except Exception:
            return _UNKNOWN_CONCRETE
    if isinstance(value, PhiValue):
        concrete_values = tuple(
            concrete_from_abstract(
                item,
                inputs,
                input_context=input_context,
            )
            for item in value.values
        )
        known = tuple(item for item in concrete_values if item is not _UNKNOWN_CONCRETE)
        if known and all(item == known[0] for item in known):
            return known[0]
    return _UNKNOWN_CONCRETE

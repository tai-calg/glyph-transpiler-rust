from __future__ import annotations

from .capabilities import (
    AggregateType,
    CapabilityFunction,
    CapabilityModel,
    CapabilityParam,
    CapabilityType,
)


_SHORTCUTS = {
    "F": "f32",
    "D": "f64",
    "U": "u16",
    "I": "i32",
    "B": "bool",
}


def _type(ty: CapabilityType) -> CapabilityType:
    return CapabilityType(
        ty.capability,
        _SHORTCUTS.get(ty.name, ty.name),
        tuple(_type(arg) for arg in ty.args),
        ty.state,
        _SHORTCUTS.get(ty.raw, ty.raw),
    )


def normalize_capability_types(model: CapabilityModel) -> CapabilityModel:
    functions = tuple(
        CapabilityFunction(
            function.name,
            function.marker,
            tuple(
                CapabilityParam(param.name, _type(param.type), param.line)
                for param in function.params
            ),
            _type(function.result),
            function.line,
            function.body_start,
            function.body_end,
        )
        for function in model.functions
    )
    aggregates = tuple(
        AggregateType(
            aggregate.name,
            tuple(_type(member) for member in aggregate.members),
            aggregate.line,
        )
        for aggregate in model.aggregates
    )
    return CapabilityModel(
        model.resources,
        functions,
        aggregates,
        model.operations,
    )

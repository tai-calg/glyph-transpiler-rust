from __future__ import annotations

from .capabilities import (
    AggregateType,
    CapabilityFunction,
    CapabilityModel,
    CapabilityParam,
    CapabilityType,
)
from .type_shortcuts import expand_type_name, expand_type_tokens


def _normalize_type(ty: CapabilityType) -> CapabilityType:
    return CapabilityType(
        ty.capability,
        expand_type_name(ty.name),
        tuple(_normalize_type(argument) for argument in ty.args),
        ty.state,
        expand_type_tokens(ty.raw),
    )


def normalize_capability_types(model: CapabilityModel) -> CapabilityModel:
    """Normalize Capability IR with the same shortcut rules as Plain Glyph."""

    functions = tuple(
        CapabilityFunction(
            function.name,
            function.marker,
            tuple(
                CapabilityParam(
                    parameter.name,
                    _normalize_type(parameter.type),
                    parameter.line,
                )
                for parameter in function.params
            ),
            _normalize_type(function.result),
            function.line,
            function.body_start,
            function.body_end,
        )
        for function in model.functions
    )
    aggregates = tuple(
        AggregateType(
            aggregate.name,
            tuple(_normalize_type(member) for member in aggregate.members),
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

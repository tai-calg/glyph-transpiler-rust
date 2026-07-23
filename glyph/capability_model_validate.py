from __future__ import annotations

from collections import Counter
from typing import Mapping

from .capabilities import (
    AggregateType,
    CapabilityKind,
    CapabilityModel,
    CapabilityType,
)
from .compiler import GlyphError


def _resource_occurrences(
    ty: CapabilityType,
    resources: set[str],
    aggregates: Mapping[str, AggregateType],
    seen: set[str] | None = None,
) -> list[CapabilityType]:
    result: list[CapabilityType] = []
    if ty.name in resources:
        result.append(ty)
    for argument in ty.args:
        result.extend(_resource_occurrences(argument, resources, aggregates, seen))
    aggregate = aggregates.get(ty.name)
    if aggregate is not None:
        visited = set() if seen is None else set(seen)
        if ty.name not in visited:
            visited.add(ty.name)
            for member in aggregate.members:
                result.extend(
                    _resource_occurrences(member, resources, aggregates, visited)
                )
    return result


def validate_capability_model(model: CapabilityModel) -> None:
    resources = {item.name for item in model.resources}
    aggregates = {item.name: item for item in model.aggregates}

    for function in model.functions:
        outputs = _resource_occurrences(
            function.result,
            resources,
            aggregates,
        )
        inputs = [
            parameter.type
            for parameter in function.params
            if parameter.type.name in resources
        ]

        same_type_owned = Counter(
            item.name
            for item in inputs
            if item.capability is CapabilityKind.OWN
        )
        output_types = Counter(item.name for item in outputs)
        for name, count in same_type_owned.items():
            if count > 1 and output_types[name]:
                raise GlyphError(
                    f"{function.line}行目: '{function.name}' は同型own resource '{name}' を"
                    "複数受け取るため、出力identity対応をContractで明示する必要がある"
                )

        for source in inputs:
            related = [item for item in outputs if item.name == source.name]
            if source.capability in {CapabilityKind.SHARE, CapabilityKind.LINK}:
                for target in related:
                    if target.capability is CapabilityKind.OWN:
                        raise GlyphError(
                            f"{function.line}行目: {source.capability.value} resourceから"
                            " own resourceへ昇格できない"
                        )
                    if target.state != source.state:
                        raise GlyphError(
                            f"{function.line}行目: {source.capability.value} resource"
                            f" '{source.name}[{source.state}]' のstateを"
                            f" '[{target.state}]' へ変更できない"
                        )
            if source.capability is CapabilityKind.OWN:
                for target in related:
                    if target.capability is CapabilityKind.LINK:
                        raise GlyphError(
                            f"{function.line}行目: own resourceを直接linkへ変換できない。"
                            "shareへ公開してからlinkを生成する"
                        )

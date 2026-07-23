from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .capabilities import AggregateType, CapabilityModel, CapabilityType
from .schema import IR_SCHEMA_VERSION, RESOURCE_FLOW_IR_SCHEMA


@dataclass(frozen=True)
class ResourceEndpoint:
    place: str
    resource: str
    state: str
    capability: str
    identity: str

    def to_dict(self) -> dict[str, object]:
        return {
            "place": self.place,
            "resource": self.resource,
            "state": self.state,
            "capability": self.capability,
            "identity": self.identity,
        }


@dataclass(frozen=True)
class ResourceTransition:
    function: str
    identity: str
    source: ResourceEndpoint | None
    target: ResourceEndpoint
    kind: str
    line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "function": self.function,
            "identity": self.identity,
            "source": None if self.source is None else self.source.to_dict(),
            "target": self.target.to_dict(),
            "kind": self.kind,
            "line": self.line,
        }


@dataclass(frozen=True)
class ResourceFlowModel:
    transitions: tuple[ResourceTransition, ...] = ()

    @classmethod
    def empty(cls) -> "ResourceFlowModel":
        return cls()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": RESOURCE_FLOW_IR_SCHEMA,
            "version": IR_SCHEMA_VERSION,
            "transitions": [item.to_dict() for item in self.transitions],
        }


def _outputs(
    ty: CapabilityType,
    resources: set[str],
    aggregates: Mapping[str, AggregateType],
    path: str,
    seen: set[str] | None = None,
) -> list[tuple[str, CapabilityType]]:
    output: list[tuple[str, CapabilityType]] = []
    if ty.name in resources:
        output.append((path, ty))
    if ty.name == "result" and len(ty.args) == 2:
        output.extend(_outputs(ty.args[0], resources, aggregates, path + ".ok", seen))
        output.extend(_outputs(ty.args[1], resources, aggregates, path + ".err", seen))
        return output
    if ty.name == "tuple":
        for index, argument in enumerate(ty.args):
            output.extend(
                _outputs(argument, resources, aggregates, f"{path}.{index}", seen)
            )
        return output
    for index, argument in enumerate(ty.args):
        output.extend(
            _outputs(argument, resources, aggregates, f"{path}.arg{index}", seen)
        )
    aggregate = aggregates.get(ty.name)
    if aggregate is not None:
        visited = set() if seen is None else set(seen)
        if ty.name not in visited:
            visited.add(ty.name)
            for index, member in enumerate(aggregate.members):
                output.extend(
                    _outputs(
                        member,
                        resources,
                        aggregates,
                        f"{path}.{ty.name}[{index}]",
                        visited,
                    )
                )
    return output


def _input_resources(
    function_name: str,
    parameters,
    resources: set[str],
) -> dict[str, list[ResourceEndpoint]]:
    result: dict[str, list[ResourceEndpoint]] = {}
    for parameter in parameters:
        ty = parameter.type
        if ty.name not in resources:
            continue
        endpoint = ResourceEndpoint(
            parameter.name,
            ty.name,
            ty.state or "?",
            ty.capability.value,
            f"rho:{function_name}:{parameter.name}",
        )
        result.setdefault(ty.name, []).append(endpoint)
    return result


def build_resource_flow(model: CapabilityModel) -> ResourceFlowModel:
    resources = {item.name for item in model.resources}
    aggregates = {item.name: item for item in model.aggregates}
    transitions: list[ResourceTransition] = []

    for function in model.functions:
        inputs = _input_resources(function.name, function.params, resources)
        fresh_index = 0
        for path, ty in _outputs(
            function.result,
            resources,
            aggregates,
            "return",
        ):
            candidates = inputs.get(ty.name, [])
            if len(candidates) > 1:
                raise ValueError(
                    f"ambiguous resource identity in {function.name}: {ty.name}"
                )
            source = candidates[0] if candidates else None
            if source is None:
                identity = f"rho:{function.name}:fresh:{fresh_index}"
                fresh_index += 1
                kind = "create"
            else:
                identity = source.identity
                kind = "preserve" if source.state == (ty.state or "?") else "transition"
            target = ResourceEndpoint(
                path,
                ty.name,
                ty.state or "?",
                ty.capability.value,
                identity,
            )
            transitions.append(
                ResourceTransition(
                    function.name,
                    identity,
                    source,
                    target,
                    kind,
                    function.line,
                )
            )

    return ResourceFlowModel(tuple(transitions))

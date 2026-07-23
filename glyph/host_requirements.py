from __future__ import annotations

from dataclasses import dataclass

from .capabilities import CapabilityModel, CapabilityType
from .contract_semantics import ContractSemanticModel
from .resource_flow import ResourceEndpoint, ResourceFlowModel
from .schema import HOST_REQUIREMENTS_IR_SCHEMA, IR_SCHEMA_VERSION


@dataclass(frozen=True)
class HostTypeRef:
    name: str
    capability: str = "plain"
    state: str | None = None
    arguments: tuple["HostTypeRef", ...] = ()

    @classmethod
    def from_capability(cls, value: CapabilityType) -> "HostTypeRef":
        return cls(
            value.name,
            value.capability.value,
            value.state,
            tuple(cls.from_capability(argument) for argument in value.args),
        )

    @classmethod
    def from_endpoint(cls, value: ResourceEndpoint) -> "HostTypeRef":
        return cls(value.resource, value.capability, value.state)

    def canonical_key(self) -> str:
        arguments = ""
        if self.arguments:
            arguments = "<" + ",".join(
                argument.canonical_key() for argument in self.arguments
            ) + ">"
        state = "" if self.state is None else f"[{self.state}]"
        return f"{self.capability}:{self.name}{arguments}{state}"

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "capability": self.capability,
            "state": self.state,
            "arguments": [argument.to_dict() for argument in self.arguments],
        }


@dataclass(frozen=True)
class RepresentationSlot:
    id: str
    associated_type: str
    type: HostTypeRef
    world: str | None
    origins: tuple[str, ...]
    line: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "associated_type": self.associated_type,
            "type": self.type.to_dict(),
            "world": self.world,
            "origins": list(self.origins),
            "line": self.line,
        }


@dataclass(frozen=True)
class HostPort:
    name: str
    type: HostTypeRef
    representation: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": self.type.to_dict(),
            "representation": self.representation,
        }


@dataclass(frozen=True)
class HostOperationRequirement:
    id: str
    kind: str
    subject: str
    contract: str | None
    inputs: tuple[HostPort, ...]
    outputs: tuple[HostPort, ...]
    attributes: tuple[tuple[str, str], ...]
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    may_fail: bool
    verification_classes: tuple[str, ...]
    line: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "subject": self.subject,
            "contract": self.contract,
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "attributes": {key: value for key, value in self.attributes},
            "preconditions": list(self.preconditions),
            "postconditions": list(self.postconditions),
            "may_fail": self.may_fail,
            "verification_classes": list(self.verification_classes),
            "line": self.line,
        }


@dataclass(frozen=True)
class HostInvariant:
    id: str
    statement: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "statement": self.statement}


@dataclass(frozen=True)
class HostRequirementModel:
    representations: tuple[RepresentationSlot, ...] = ()
    operations: tuple[HostOperationRequirement, ...] = ()
    invariants: tuple[HostInvariant, ...] = ()

    @classmethod
    def empty(cls) -> "HostRequirementModel":
        return cls()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": HOST_REQUIREMENTS_IR_SCHEMA,
            "version": IR_SCHEMA_VERSION,
            "representations": [item.to_dict() for item in self.representations],
            "operations": [item.to_dict() for item in self.operations],
            "invariants": [item.to_dict() for item in self.invariants],
        }


def build_host_requirements(
    capabilities: CapabilityModel,
    runtime: ContractSemanticModel,
    resource_flow: ResourceFlowModel,
) -> HostRequirementModel:
    """Derive Host requirements without making the IR depend on its builder."""

    from .host_requirement_builder import build_host_requirements as build

    return build(capabilities, runtime, resource_flow)

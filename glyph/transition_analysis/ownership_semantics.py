from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..artifacts import CompilationModel
from ..capabilities import CapabilityKind, CapabilityOperation, CapabilityType
from .abstract_store import AbstractLocation
from .exactness import (
    Approximation,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)


OWNERSHIP_SEMANTICS_VERSION = 1


class OwnershipAvailability(str, Enum):
    AVAILABLE = "available"
    MOVED = "moved"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OwnershipBinding:
    name: str
    capability: CapabilityKind
    resource: str
    state: str | None
    availability: OwnershipAvailability

    def to_ir(self) -> dict[str, object]:
        return {
            "name": self.name,
            "capability": self.capability.value,
            "resource": self.resource,
            "state": self.state,
            "availability": self.availability.value,
        }


@dataclass(frozen=True)
class OwnershipFootprint:
    reads: tuple[AbstractLocation, ...]
    writes: tuple[AbstractLocation, ...]
    moves: tuple[AbstractLocation, ...]

    def to_ir(self) -> dict[str, object]:
        return {
            "reads": [_location_ir(item) for item in self.reads],
            "writes": [_location_ir(item) for item in self.writes],
            "moves": [_location_ir(item) for item in self.moves],
        }


@dataclass(frozen=True)
class OwnershipViolation:
    code: str
    function: str
    source: str | None
    line: int

    def to_ir(self) -> dict[str, object]:
        return {
            "code": self.code,
            "function": self.function,
            "source": self.source,
            "line": self.line,
        }


@dataclass(frozen=True)
class OwnershipFunctionSummary:
    function: str
    initial: tuple[OwnershipBinding, ...]
    final: tuple[OwnershipBinding, ...]
    footprint: OwnershipFootprint
    operations: tuple[CapabilityOperation, ...]
    violations: tuple[OwnershipViolation, ...]
    approximation: Approximation

    def to_ir(self) -> dict[str, object]:
        return {
            "version": OWNERSHIP_SEMANTICS_VERSION,
            "function": self.function,
            "initial": [item.to_ir() for item in self.initial],
            "final": [item.to_ir() for item in self.final],
            "footprint": self.footprint.to_ir(),
            "operations": [item.to_dict() for item in self.operations],
            "violations": [item.to_ir() for item in self.violations],
            "approximation": self.approximation.to_ir(),
        }


def build_ownership_summaries(
    model: CompilationModel,
) -> dict[str, OwnershipFunctionSummary]:
    capability_model = model.capabilities
    functions = {item.name: item for item in capability_model.functions}
    operations_by_function: dict[str, list[CapabilityOperation]] = {}
    for operation in capability_model.operations:
        operations_by_function.setdefault(operation.function, []).append(operation)

    summaries: dict[str, OwnershipFunctionSummary] = {}
    for name, function in functions.items():
        initial_map = {
            parameter.name: _binding(parameter.name, parameter.type)
            for parameter in function.params
            if parameter.type.capability is not CapabilityKind.PLAIN
        }
        current = dict(initial_map)
        reads: set[AbstractLocation] = set()
        writes: set[AbstractLocation] = set()
        moves: set[AbstractLocation] = set()
        violations: list[OwnershipViolation] = []
        operations = tuple(
            sorted(
                operations_by_function.get(name, ()),
                key=lambda item: (item.line, item.kind, item.source or ""),
            )
        )

        for operation in operations:
            source = current.get(operation.source or "")
            location = _location(name, operation.source)
            if operation.kind == "move":
                if source is None or source.availability is not OwnershipAvailability.AVAILABLE:
                    violations.append(
                        OwnershipViolation(
                            "move-from-unavailable",
                            name,
                            operation.source,
                            operation.line,
                        )
                    )
                    continue
                moves.add(location)
                writes.add(location)
                current[source.name] = _replace_availability(
                    source,
                    OwnershipAvailability.MOVED,
                )
                if operation.target:
                    current[operation.target] = _replace_name(source, operation.target)
                continue

            if operation.kind == "borrow":
                if source is None or source.availability is not OwnershipAvailability.AVAILABLE:
                    violations.append(
                        OwnershipViolation(
                            "borrow-from-unavailable",
                            name,
                            operation.source,
                            operation.line,
                        )
                    )
                else:
                    reads.add(location)
                continue

            if operation.kind == "borrow_mut":
                if source is None or source.availability is not OwnershipAvailability.AVAILABLE:
                    violations.append(
                        OwnershipViolation(
                            "mutable-borrow-from-unavailable",
                            name,
                            operation.source,
                            operation.line,
                        )
                    )
                elif source.capability in {CapabilityKind.SHARE, CapabilityKind.LINK}:
                    violations.append(
                        OwnershipViolation(
                            "mutable-borrow-from-nonexclusive-capability",
                            name,
                            operation.source,
                            operation.line,
                        )
                    )
                else:
                    reads.add(location)
                    writes.add(location)
                continue

            if operation.kind == "capability_cast":
                if source is None or source.availability is not OwnershipAvailability.AVAILABLE:
                    violations.append(
                        OwnershipViolation(
                            "cast-from-unavailable",
                            name,
                            operation.source,
                            operation.line,
                        )
                    )
                    continue
                reads.add(location)
                if operation.target:
                    target_kind = _capability_kind(operation.capability)
                    current[operation.target] = OwnershipBinding(
                        operation.target,
                        target_kind or source.capability,
                        source.resource,
                        source.state,
                        OwnershipAvailability.AVAILABLE,
                    )
                continue

            violations.append(
                OwnershipViolation(
                    "unknown-capability-operation",
                    name,
                    operation.source,
                    operation.line,
                )
            )

        approximation = (
            Approximation.exact(
                ExactnessProof(
                    ExactnessProofKind.STRUCTURAL_IDENTITY,
                    ExactnessProofScope.FUNCTION_SUMMARY,
                    f"Capability IR ownership replay for {name}",
                )
            )
            if not violations
            else Approximation.unknown(
                *(violation.code for violation in violations)
            )
        )
        summaries[name] = OwnershipFunctionSummary(
            name,
            tuple(sorted(initial_map.values(), key=lambda item: item.name)),
            tuple(sorted(current.values(), key=lambda item: item.name)),
            OwnershipFootprint(
                tuple(sorted(reads, key=_location_key)),
                tuple(sorted(writes, key=_location_key)),
                tuple(sorted(moves, key=_location_key)),
            ),
            operations,
            tuple(violations),
            approximation,
        )
    return summaries


def _binding(name: str, type_ref: CapabilityType) -> OwnershipBinding:
    return OwnershipBinding(
        name,
        type_ref.capability,
        type_ref.name,
        type_ref.state,
        OwnershipAvailability.AVAILABLE,
    )


def _replace_availability(
    binding: OwnershipBinding,
    availability: OwnershipAvailability,
) -> OwnershipBinding:
    return OwnershipBinding(
        binding.name,
        binding.capability,
        binding.resource,
        binding.state,
        availability,
    )


def _replace_name(
    binding: OwnershipBinding,
    name: str,
) -> OwnershipBinding:
    return OwnershipBinding(
        name,
        binding.capability,
        binding.resource,
        binding.state,
        OwnershipAvailability.AVAILABLE,
    )


def _location(function: str, source: str | None) -> AbstractLocation:
    return AbstractLocation("resource", f"{function}:{source or '?'}")


def _location_key(location: AbstractLocation) -> tuple[str, str]:
    return location.kind, location.key


def _location_ir(location: AbstractLocation) -> dict[str, str]:
    return {"kind": location.kind, "key": location.key}


def _capability_kind(value: str | None) -> CapabilityKind | None:
    if not value:
        return None
    try:
        return CapabilityKind(value)
    except ValueError:
        return None

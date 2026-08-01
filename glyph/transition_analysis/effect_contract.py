from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .abstract_store import AbstractLocation
from .abstract_value import (
    AbstractValue,
    ApplicationValue,
    BottomValue,
    ConstantValue,
    ConstructorValue,
    FieldValue,
    ParameterValue,
    PhiValue,
    TopValue,
)
from .concrete import EffectHandler
from .effect_summary import EffectSummary, EffectWrite, identity_effect_summary
from .exactness import (
    Approximation,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)
from .summary_interpreter import ContextualEffectSummaryRegistry


EFFECT_CONTRACT_REGISTRY_VERSION = 2


@dataclass(frozen=True)
class VerifiedEffectContract:
    """One reviewed abstract/concrete contract for an external Effect.

    Witness generation is allowed to execute only handlers paired with an exact
    abstract summary. A handler alone is not evidence, and an abstract summary
    alone is insufficient for concrete replay.

    ``failure_values`` records the reviewed failure vocabulary of the operation.
    It is empty for the deterministic public strict surface. Failure-capable
    operations must not be admitted to that surface until their exact result
    relation is represented by the analyzer.
    """

    operation: str
    summary: EffectSummary
    handler: EffectHandler
    source: str
    failure_values: tuple[str, ...] = ()
    review_notes: str = ""

    def __post_init__(self) -> None:
        if not self.operation.strip():
            raise ValueError("Effect contract operation must not be empty")
        if self.summary.operation != self.operation:
            raise ValueError(
                "Effect contract operation does not match summary operation: "
                f"{self.operation} != {self.summary.operation}"
            )
        if not self.summary.approximation.is_exact:
            raise ValueError("Verified Effect contract requires an exact summary")
        if self.summary.unknown_write_footprint:
            raise ValueError(
                "Verified Effect contract cannot have an unknown write footprint"
            )
        if "unknown" in self.summary.completions:
            raise ValueError(
                "Verified Effect contract cannot contain unknown completion"
            )
        if not self.source.strip():
            raise ValueError("Effect contract source must not be empty")
        normalized_failures = tuple(sorted(set(self.failure_values)))
        object.__setattr__(self, "failure_values", normalized_failures)

    def to_ir(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "parameters": list(self.summary.parameters),
            "return_value": _abstract_value_ir(self.summary.return_value),
            "failure_values": list(self.failure_values),
            "completions": list(self.summary.completions),
            "reads": [_location_ir(item) for item in self.summary.reads],
            "writes": [_write_ir(item) for item in self.summary.writes],
            "unknown_write_footprint": self.summary.unknown_write_footprint,
            "source": self.source,
            "review_notes": self.review_notes or None,
            "approximation": self.summary.approximation.to_ir(),
        }


@dataclass(frozen=True)
class VerifiedEffectContractRegistry:
    """Resolve reviewed Effect contracts without leaking one entry into another."""

    defaults: tuple[tuple[str, VerifiedEffectContract], ...] = ()
    by_entry: tuple[
        tuple[str, tuple[tuple[str, VerifiedEffectContract], ...]], ...
    ] = ()

    def __post_init__(self) -> None:
        _validate_contract_pairs(self.defaults, context="default")
        seen_entries: set[str] = set()
        for entry, contracts in self.by_entry:
            if not entry.strip():
                raise ValueError("Effect contract entry must not be empty")
            if entry in seen_entries:
                raise ValueError(f"duplicate Effect contract entry {entry}")
            seen_entries.add(entry)
            _validate_contract_pairs(contracts, context=entry)

    def resolve(self, entry: str) -> dict[str, VerifiedEffectContract]:
        result = dict(self.defaults)
        for candidate, contracts in self.by_entry:
            if candidate == entry:
                result.update(dict(contracts))
                break
        return result

    def summaries(self, entry: str) -> dict[str, EffectSummary]:
        return {
            operation: contract.summary
            for operation, contract in self.resolve(entry).items()
        }

    def handlers(self, entry: str) -> dict[str, EffectHandler]:
        return {
            operation: contract.handler
            for operation, contract in self.resolve(entry).items()
        }

    def abstract_registry(self) -> ContextualEffectSummaryRegistry:
        return ContextualEffectSummaryRegistry(
            defaults=tuple(
                (operation, contract.summary)
                for operation, contract in self.defaults
            ),
            by_entry=tuple(
                (
                    entry,
                    tuple(
                        (operation, contract.summary)
                        for operation, contract in contracts
                    ),
                )
                for entry, contracts in self.by_entry
            ),
        )

    def to_ir(self) -> dict[str, object]:
        return {
            "version": EFFECT_CONTRACT_REGISTRY_VERSION,
            "defaults": [contract.to_ir() for _, contract in self.defaults],
            "by_entry": [
                {
                    "entry": entry,
                    "contracts": [contract.to_ir() for _, contract in contracts],
                }
                for entry, contracts in self.by_entry
            ],
        }


def reviewed_deterministic_contract(
    operation: str,
    parameters: tuple[str, ...],
    return_value: AbstractValue,
    handler: EffectHandler,
    *,
    source: str,
    reads: tuple[AbstractLocation, ...] = (),
    writes: tuple[EffectWrite, ...] = (),
    review_notes: str = "",
) -> VerifiedEffectContract:
    """Build one exact deterministic contract from a reviewed release spec."""

    approximation = Approximation.exact(
        ExactnessProof(
            ExactnessProofKind.REVIEWED_CONTRACT,
            ExactnessProofScope.EFFECT_CONTRACT,
            source,
        )
    )
    summary = EffectSummary(
        operation=operation,
        parameters=parameters,
        return_value=return_value,
        reads=reads,
        writes=writes,
        completions=("normal",),
        approximation=approximation,
    )
    return VerifiedEffectContract(
        operation,
        summary,
        handler,
        source,
        failure_values=(),
        review_notes=review_notes,
    )


def read_only_identity_contract(
    operation: str,
    parameter: str,
    *,
    source: str,
) -> VerifiedEffectContract:
    """Build an explicitly reviewed, deterministic, read-only identity contract."""

    approximation = Approximation.exact(
        ExactnessProof(
            ExactnessProofKind.STRUCTURAL_IDENTITY,
            ExactnessProofScope.EFFECT_CONTRACT,
            f"reviewed read-only identity Effect contract for {operation}",
        )
    )
    summary = identity_effect_summary(
        operation,
        parameter,
        approximation=approximation,
    )

    def handler(arguments: tuple[object, ...]) -> object:
        if len(arguments) != 1:
            raise ValueError(
                f"identity Effect {operation} expects one argument, got {len(arguments)}"
            )
        return arguments[0]

    return VerifiedEffectContract(operation, summary, handler, source)


def _validate_contract_pairs(
    pairs: tuple[tuple[str, VerifiedEffectContract], ...],
    *,
    context: str,
) -> None:
    seen: set[str] = set()
    for operation, contract in pairs:
        if operation in seen:
            raise ValueError(f"duplicate Effect contract {operation} in {context}")
        seen.add(operation)
        if operation != contract.operation:
            raise ValueError(
                f"Effect contract key {operation} does not match {contract.operation}"
            )


def _location_ir(location: AbstractLocation) -> dict[str, str]:
    return {"kind": location.kind, "key": location.key}


def _write_ir(write: EffectWrite) -> dict[str, object]:
    return {
        "address": {
            "locations": [
                _location_ir(location)
                for location in sorted(write.address.locations)
            ],
            "singleton_proven": write.address.singleton_proven,
        },
        "value": None if write.value is None else _abstract_value_ir(write.value),
    }


def _abstract_value_ir(value: AbstractValue) -> dict[str, object]:
    if isinstance(value, BottomValue):
        return {"kind": "bottom"}
    if isinstance(value, ParameterValue):
        return {"kind": "parameter", "context": value.context, "name": value.name}
    if isinstance(value, ConstantValue):
        item = value.value
        if not isinstance(item, (str, int, float, bool, type(None))):
            item = repr(item)
        return {"kind": "constant", "value": item}
    if isinstance(value, FieldValue):
        return {
            "kind": "field",
            "base": _abstract_value_ir(value.base),
            "field": value.field,
        }
    if isinstance(value, ConstructorValue):
        return {
            "kind": "constructor",
            "type": value.type_name,
            "fields": [
                {"name": name, "value": _abstract_value_ir(argument)}
                for name, argument in zip(
                    value.field_names,
                    value.arguments,
                    strict=True,
                )
            ],
        }
    if isinstance(value, ApplicationValue):
        return {
            "kind": "application",
            "operation": value.operation,
            "arguments": [_abstract_value_ir(item) for item in value.arguments],
        }
    if isinstance(value, PhiValue):
        return {
            "kind": "phi",
            "values": [_abstract_value_ir(item) for item in value.values],
        }
    if isinstance(value, TopValue):
        return {"kind": "top", "reason": value.reason}
    raise TypeError(f"unsupported abstract value {value!r}")


__all__ = [
    "EFFECT_CONTRACT_REGISTRY_VERSION",
    "VerifiedEffectContract",
    "VerifiedEffectContractRegistry",
    "read_only_identity_contract",
    "reviewed_deterministic_contract",
]

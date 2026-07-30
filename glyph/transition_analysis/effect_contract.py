from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .concrete import EffectHandler
from .effect_summary import EffectSummary, identity_effect_summary
from .exactness import (
    Approximation,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)
from .summary_interpreter import ContextualEffectSummaryRegistry


EFFECT_CONTRACT_REGISTRY_VERSION = 1


@dataclass(frozen=True)
class VerifiedEffectContract:
    """One reviewed abstract/concrete contract for an external Effect.

    Witness generation is allowed to execute only handlers paired with an exact
    abstract summary.  A handler alone is not evidence, and an abstract summary
    alone is insufficient for concrete replay.
    """

    operation: str
    summary: EffectSummary
    handler: EffectHandler
    source: str

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

    def to_ir(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "parameters": list(self.summary.parameters),
            "completions": list(self.summary.completions),
            "read_count": len(self.summary.reads),
            "write_count": len(self.summary.writes),
            "source": self.source,
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


__all__ = [
    "EFFECT_CONTRACT_REGISTRY_VERSION",
    "VerifiedEffectContract",
    "VerifiedEffectContractRegistry",
    "read_only_identity_contract",
]

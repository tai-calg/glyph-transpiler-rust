from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from .exactness import Approximation


EXECUTION_EVIDENCE_SCHEMA = "glyph.execution-evidence"
EXECUTION_EVIDENCE_VERSION = 2


class ReachabilityStatus(str, Enum):
    PROVEN_UNREACHABLE = "proven-unreachable"
    PROVEN_REACHABLE = "proven-reachable"
    MAY_REACHABLE = "may-reachable"
    UNKNOWN = "unknown"


class CallUpperBound(str, Enum):
    ZERO = "zero"
    AT_MOST_ONE = "at-most-one"
    MANY = "many"
    UNKNOWN = "unknown"


class CompletionKind(str, Enum):
    NORMAL = "normal"
    PROPAGATED_FAILURE = "propagated-failure"
    TERMINATED = "terminated"
    DIVERGED = "diverged"
    NO_CONTINUATION = "no-continuation"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EffectEvent:
    operation: str | None
    expression: str
    failure_type: str | None = None

    def to_ir(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "expression": self.expression,
            "failure_type": self.failure_type,
        }


@dataclass(frozen=True)
class TraceAlternative:
    condition: str | None
    events: tuple[EffectEvent, ...]

    def to_ir(self) -> dict[str, object]:
        return {
            "condition": self.condition,
            "events": [event.to_ir() for event in self.events],
        }


@dataclass(frozen=True)
class EffectTraceEvidence:
    alternatives: tuple[TraceAlternative, ...]
    approximation: Approximation

    @property
    def is_singleton(self) -> bool:
        if not self.approximation.is_exact or len(self.alternatives) != 1:
            return False
        return self.alternatives[0].condition in (None, "", "true")

    def to_ir(self) -> dict[str, object]:
        return {
            "alternatives": [alternative.to_ir() for alternative in self.alternatives],
            "is_singleton": self.is_singleton,
            "approximation": self.approximation.to_ir(),
        }


@dataclass(frozen=True)
class ReachabilityEvidence:
    status: ReachabilityStatus
    precondition: str | None
    witness: Mapping[str, object] | None
    approximation: Approximation

    def to_ir(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "precondition": self.precondition,
            "witness": dict(self.witness) if self.witness is not None else None,
            "approximation": self.approximation.to_ir(),
        }


@dataclass(frozen=True)
class CallCardinalityEvidence:
    upper_bound: CallUpperBound
    witness: Mapping[str, object] | None
    approximation: Approximation

    def to_ir(self) -> dict[str, object]:
        return {
            "upper_bound": self.upper_bound.value,
            "witness": dict(self.witness) if self.witness is not None else None,
            "approximation": self.approximation.to_ir(),
        }


@dataclass(frozen=True)
class CompletionEvidence:
    kinds: tuple[CompletionKind, ...]
    approximation: Approximation

    def __post_init__(self) -> None:
        if not self.kinds:
            raise ValueError("Completion evidence must contain at least one kind")
        normalized = tuple(sorted(set(self.kinds), key=lambda item: item.value))
        object.__setattr__(self, "kinds", normalized)

    def to_ir(self) -> dict[str, object]:
        return {
            "kinds": [kind.value for kind in self.kinds],
            "approximation": self.approximation.to_ir(),
        }


@dataclass(frozen=True)
class ContextExecutionEvidence:
    system: str | None
    entry: str
    scope: str
    reachability: ReachabilityEvidence
    cardinality: CallCardinalityEvidence
    effect_trace: EffectTraceEvidence
    completion: CompletionEvidence
    unknown_reasons: tuple[str, ...] = ()
    legacy_action: Mapping[str, object] | None = None

    def to_ir(self) -> dict[str, object]:
        return {
            "system": self.system,
            "entry": self.entry,
            "scope": self.scope,
            "reachability": self.reachability.to_ir(),
            "cardinality": self.cardinality.to_ir(),
            "effect_trace": self.effect_trace.to_ir(),
            "completion": self.completion.to_ir(),
            "unknown_reasons": list(self.unknown_reasons),
            "legacy_action": (
                dict(self.legacy_action) if self.legacy_action is not None else None
            ),
        }


@dataclass(frozen=True)
class EdgeExecutionEvidence:
    edge_id: str
    synthesized_failure: bool
    contexts: tuple[ContextExecutionEvidence, ...]
    completion: CompletionEvidence
    approximation: Approximation

    def to_ir(self) -> dict[str, object]:
        return {
            "schema": EXECUTION_EVIDENCE_SCHEMA,
            "version": EXECUTION_EVIDENCE_VERSION,
            "edge_id": self.edge_id,
            "synthesized_failure": self.synthesized_failure,
            "contexts": [context.to_ir() for context in self.contexts],
            "completion": self.completion.to_ir(),
            "approximation": self.approximation.to_ir(),
        }


def effect_events(invocations: Sequence[Mapping[str, object]]) -> tuple[EffectEvent, ...]:
    return tuple(
        EffectEvent(
            operation=_optional_text(invocation.get("operation")),
            expression=str(invocation.get("expression") or ""),
            failure_type=_optional_text(invocation.get("failure_type")),
        )
        for invocation in invocations
        if invocation.get("expression") or invocation.get("operation")
    )


def _optional_text(value: object) -> str | None:
    text = str(value) if value is not None else ""
    return text or None

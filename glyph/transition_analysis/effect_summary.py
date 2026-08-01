from __future__ import annotations

from dataclasses import dataclass

from .abstract_store import AbstractAddress, AbstractLocation, AbstractStore
from .abstract_value import AbstractValue, ParameterValue, TopValue, substitute_value
from .exactness import Approximation, ApproximationCause


@dataclass(frozen=True)
class EffectWrite:
    address: AbstractAddress
    value: AbstractValue | None = None


@dataclass(frozen=True)
class EffectSummary:
    operation: str
    parameters: tuple[str, ...]
    return_value: AbstractValue
    reads: tuple[AbstractLocation, ...]
    writes: tuple[EffectWrite, ...]
    completions: tuple[str, ...]
    approximation: Approximation
    unknown_write_footprint: bool = False


@dataclass(frozen=True)
class AbstractEffectEvent:
    operation: str
    arguments: tuple[AbstractValue, ...]


@dataclass(frozen=True)
class EffectApplication:
    result: AbstractValue
    store: AbstractStore
    event: AbstractEffectEvent
    completions: tuple[str, ...]
    approximation: Approximation


def apply_effect_summary(
    summary: EffectSummary,
    arguments: tuple[AbstractValue, ...],
    store: AbstractStore,
) -> EffectApplication:
    """Apply one summary; uncertainty can only widen state and completion."""

    if len(arguments) != len(summary.parameters):
        approximation = Approximation.unknown("effect-summary-arity-mismatch")
        return EffectApplication(
            TopValue("effect-summary-arity-mismatch"),
            store.havoc(
                (AbstractLocation("external", summary.operation),),
                reason="effect-summary-arity-mismatch",
            ),
            AbstractEffectEvent(summary.operation, arguments),
            ("normal", "propagated-failure", "unknown"),
            approximation,
        )

    substitution = dict(zip(summary.parameters, arguments, strict=True))
    result = substitute_value(summary.return_value, substitution)
    next_store = store
    if summary.unknown_write_footprint:
        known_locations = tuple(next_store.mapping)
        if known_locations:
            next_store = next_store.havoc(
                known_locations,
                reason=ApproximationCause.UNKNOWN_EFFECT_FOOTPRINT.value,
            )
        next_store = next_store.write(
            AbstractAddress(
                frozenset({AbstractLocation("external", summary.operation)}),
                singleton_proven=True,
            ),
            TopValue(ApproximationCause.UNKNOWN_EFFECT_FOOTPRINT.value),
        )
    else:
        for write in summary.writes:
            value = (
                TopValue("effect-write-value-unknown")
                if write.value is None
                else substitute_value(write.value, substitution)
            )
            next_store = next_store.write(write.address, value)

    approximation = Approximation.combine(
        (summary.approximation, next_store.approximation)
    )
    if summary.unknown_write_footprint and approximation.is_exact:
        approximation = approximation.degrade(
            ApproximationCause.UNKNOWN_EFFECT_FOOTPRINT,
            unknown=True,
        )
    return EffectApplication(
        result,
        next_store,
        AbstractEffectEvent(summary.operation, arguments),
        summary.completions,
        approximation,
    )


def unknown_effect_summary(
    operation: str,
    parameters: tuple[str, ...],
) -> EffectSummary:
    """Safe fallback for an Effect without a verified contract."""

    return EffectSummary(
        operation=operation,
        parameters=parameters,
        return_value=TopValue(ApproximationCause.UNKNOWN_EFFECT_RESULT.value),
        reads=(),
        writes=(),
        completions=("normal", "propagated-failure", "unknown"),
        approximation=Approximation.unknown(
            ApproximationCause.UNKNOWN_EFFECT_RESULT,
            ApproximationCause.UNKNOWN_EFFECT_FOOTPRINT,
        ),
        unknown_write_footprint=True,
    )


def identity_effect_summary(
    operation: str,
    parameter: str,
    *,
    approximation: Approximation,
) -> EffectSummary:
    """Convenience contract for a verified read-only identity Effect."""

    return EffectSummary(
        operation=operation,
        parameters=(parameter,),
        return_value=ParameterValue(operation, parameter),
        reads=(),
        writes=(),
        completions=("normal",),
        approximation=approximation,
    )

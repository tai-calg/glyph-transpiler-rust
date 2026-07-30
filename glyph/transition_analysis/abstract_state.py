from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from ..compiler import BoolExpr, Expr, NameExpr
from .abstract_store import AbstractStore
from .abstract_value import AbstractValue, BottomValue, TopValue, join_values
from .effect_summary import AbstractEffectEvent
from .exactness import Approximation, ApproximationCause


@dataclass(frozen=True)
class AbstractTransitionEvent:
    machine: str
    function: str
    edge_id: str
    arguments: tuple[AbstractValue, ...]
    result: AbstractValue


@dataclass(frozen=True)
class GuardedAlternative:
    """One correlated path partition at a TEIR program point."""

    path_condition: Expr
    environment: tuple[tuple[str, AbstractValue], ...]
    symbolic_environment: tuple[tuple[str, Expr], ...]
    store: AbstractStore
    transition_trace: tuple[AbstractTransitionEvent, ...]
    effect_trace: tuple[AbstractEffectEvent, ...]
    completion: frozenset[str]
    return_value: AbstractValue | None
    approximation: Approximation
    unknown_reasons: tuple[str, ...] = ()
    transition_trace_top: bool = False
    effect_trace_top: bool = False

    @property
    def environment_map(self) -> dict[str, AbstractValue]:
        return dict(self.environment)

    @property
    def symbolic_map(self) -> dict[str, Expr]:
        return dict(self.symbolic_environment)

    @property
    def running(self) -> bool:
        return self.completion == frozenset({"running"})

    def bind(
        self,
        name: str,
        value: AbstractValue,
        symbolic: Expr,
        *,
        approximation: Approximation | None = None,
    ) -> "GuardedAlternative":
        environment = self.environment_map
        symbolic_environment = self.symbolic_map
        environment[name] = value
        symbolic_environment[name] = symbolic
        return replace(
            self,
            environment=_freeze_mapping(environment),
            symbolic_environment=_freeze_mapping(symbolic_environment),
            approximation=approximation or self.approximation,
        )

    def degrade(
        self,
        reason: str | ApproximationCause,
        *,
        unknown: bool = False,
        transition_trace_top: bool | None = None,
        effect_trace_top: bool | None = None,
    ) -> "GuardedAlternative":
        reason_text = reason.value if isinstance(reason, ApproximationCause) else str(reason)
        return replace(
            self,
            approximation=self.approximation.degrade(reason, unknown=unknown),
            unknown_reasons=tuple(sorted(set((*self.unknown_reasons, reason_text)))),
            transition_trace_top=(
                self.transition_trace_top
                if transition_trace_top is None
                else transition_trace_top
            ),
            effect_trace_top=(
                self.effect_trace_top if effect_trace_top is None else effect_trace_top
            ),
        )

    def to_ir(self) -> dict[str, object]:
        return {
            "path_condition": repr(self.path_condition),
            "environment": {name: repr(value) for name, value in self.environment},
            "symbolic_environment": {
                name: repr(value) for name, value in self.symbolic_environment
            },
            "store": {
                f"{location.kind}:{location.key}": repr(value)
                for location, value in self.store.bindings
            },
            "transition_trace": [
                {
                    "machine": event.machine,
                    "function": event.function,
                    "edge_id": event.edge_id,
                    "arguments": [repr(value) for value in event.arguments],
                    "result": repr(event.result),
                }
                for event in self.transition_trace
            ],
            "transition_trace_top": self.transition_trace_top,
            "effect_trace": [
                {
                    "operation": event.operation,
                    "arguments": [repr(value) for value in event.arguments],
                }
                for event in self.effect_trace
            ],
            "effect_trace_top": self.effect_trace_top,
            "completion": sorted(self.completion),
            "return_value": repr(self.return_value),
            "approximation": self.approximation.to_ir(),
            "unknown_reasons": list(self.unknown_reasons),
        }


@dataclass(frozen=True)
class AnalysisBudget:
    max_steps: int = 10_000
    max_alternatives_per_block: int = 64
    max_block_iterations: int = 32
    max_phi_values: int = 32

    def __post_init__(self) -> None:
        if min(
            self.max_steps,
            self.max_alternatives_per_block,
            self.max_block_iterations,
            self.max_phi_values,
        ) <= 0:
            raise ValueError("analysis budget values must be positive")


@dataclass(frozen=True)
class AbstractAnalysisResult:
    function: str
    completed: tuple[GuardedAlternative, ...]
    block_states: tuple[tuple[str, tuple[GuardedAlternative, ...]], ...]
    approximation: Approximation
    unknown_reasons: tuple[str, ...]

    def to_ir(self) -> dict[str, object]:
        return {
            "function": self.function,
            "completed": [item.to_ir() for item in self.completed],
            "block_states": {
                block_id: [item.to_ir() for item in alternatives]
                for block_id, alternatives in self.block_states
            },
            "approximation": self.approximation.to_ir(),
            "unknown_reasons": list(self.unknown_reasons),
        }


def initial_alternative(
    function_id: str,
    parameters: Sequence[str],
    *,
    store: AbstractStore,
    approximation: Approximation,
) -> GuardedAlternative:
    from .abstract_value import ParameterValue

    environment = {
        name: ParameterValue(function_id, name)
        for name in parameters
    }
    symbols = {name: NameExpr(name) for name in parameters}
    return GuardedAlternative(
        path_condition=BoolExpr(True),
        environment=_freeze_mapping(environment),
        symbolic_environment=_freeze_mapping(symbols),
        store=store,
        transition_trace=(),
        effect_trace=(),
        completion=frozenset({"running"}),
        return_value=None,
        approximation=approximation,
    )


def widen_alternatives(
    alternatives: Sequence[GuardedAlternative],
    *,
    max_phi_values: int,
) -> GuardedAlternative:
    if not alternatives:
        raise ValueError("cannot widen an empty alternative set")
    names = {
        name
        for alternative in alternatives
        for name, _ in alternative.environment
    }
    environment: dict[str, AbstractValue] = {}
    for name in names:
        value: AbstractValue = BottomValue()
        for alternative in alternatives:
            value = join_values(
                value,
                alternative.environment_map.get(name, BottomValue()),
                max_phi_values=max_phi_values,
            )
        environment[name] = value
    store = alternatives[0].store
    for alternative in alternatives[1:]:
        store = store.join(alternative.store)
    approximation = Approximation.combine(
        alternative.approximation for alternative in alternatives
    ).degrade(ApproximationCause.WIDENING)
    reasons = tuple(
        sorted(
            {
                ApproximationCause.WIDENING.value,
                *(
                    reason
                    for alternative in alternatives
                    for reason in alternative.unknown_reasons
                ),
            }
        )
    )
    return GuardedAlternative(
        path_condition=BoolExpr(True),
        environment=_freeze_mapping(environment),
        symbolic_environment=_freeze_mapping(
            {name: NameExpr(name) for name in names}
        ),
        store=store,
        transition_trace=(),
        effect_trace=(),
        completion=frozenset(
            {
                "running",
                "returned",
                "propagated-failure",
                "terminated",
                "diverged",
                "unknown",
            }
        ),
        return_value=TopValue(ApproximationCause.WIDENING.value),
        approximation=approximation,
        unknown_reasons=reasons,
        transition_trace_top=True,
        effect_trace_top=True,
    )


def deduplicate_alternatives(
    alternatives: Sequence[GuardedAlternative],
) -> tuple[GuardedAlternative, ...]:
    result: list[GuardedAlternative] = []
    for alternative in alternatives:
        if not any(alternative == existing for existing in result):
            result.append(alternative)
    return tuple(result)


def _freeze_mapping(mapping: Mapping[str, object]) -> tuple[tuple[str, object], ...]:
    return tuple(sorted(mapping.items(), key=lambda item: item[0]))

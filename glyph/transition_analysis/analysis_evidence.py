from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..compiler import BoolExpr
from .abstract_state import AbstractAnalysisResult, GuardedAlternative
from .concrete import ConcreteExecutionResult
from .evidence import (
    CallCardinalityEvidence,
    CallUpperBound,
    CompletionEvidence,
    CompletionKind,
    ContextExecutionEvidence,
    EdgeExecutionEvidence,
    EffectEvent,
    EffectTraceEvidence,
    ReachabilityEvidence,
    ReachabilityStatus,
    TraceAlternative,
)
from .exactness import (
    Approximation,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)


ABSTRACT_EVIDENCE_ADAPTER_VERSION = 1


@dataclass(frozen=True)
class VerifiedReachabilityWitness:
    edge_id: str
    arguments: tuple[object, ...]
    completion: str
    transition_edges: tuple[str, ...]
    source: str = "teir-concrete-replay"

    def to_ir(self) -> dict[str, object]:
        return {
            "edge_id": self.edge_id,
            "arguments": [repr(item) for item in self.arguments],
            "completion": self.completion,
            "transition_edges": list(self.transition_edges),
            "source": self.source,
        }


def verified_reachability_witness(
    execution: ConcreteExecutionResult,
    arguments: Sequence[object],
    edge_id: str,
) -> VerifiedReachabilityWitness:
    edges = tuple(event.edge_id for event in execution.transition_trace)
    if edge_id not in edges:
        raise ValueError(
            f"concrete execution did not traverse requested edge {edge_id}"
        )
    return VerifiedReachabilityWitness(
        edge_id,
        tuple(arguments),
        execution.completion,
        edges,
    )


@dataclass(frozen=True)
class AbstractEvidenceContext:
    edge_id: str
    system: str | None
    entry: str
    scope: str = "system"
    witness: VerifiedReachabilityWitness | None = None
    analysis_edge_id: str | None = None

    @property
    def source_edge_id(self) -> str:
        return self.analysis_edge_id or self.edge_id


def context_evidence_from_analysis(
    analysis: AbstractAnalysisResult,
    context: AbstractEvidenceContext,
) -> ContextExecutionEvidence:
    """Project one edge-specific abstract result into independently scoped evidence."""

    source_edge_id = context.source_edge_id
    relevant = tuple(
        alternative
        for alternative in analysis.completed
        if any(
            event.edge_id == source_edge_id
            for event in alternative.transition_trace
        )
    )
    reachability = _reachability(analysis, relevant, context)
    cardinality = _cardinality(analysis, relevant, source_edge_id)
    effect_trace = _effect_trace(analysis, relevant)
    completion = _completion(analysis, relevant)
    reasons = tuple(
        sorted(
            {
                *analysis.unknown_reasons,
                *(
                    reason
                    for alternative in relevant
                    for reason in alternative.unknown_reasons
                ),
            }
        )
    )
    return ContextExecutionEvidence(
        edge_id=context.edge_id,
        system=context.system,
        entry=context.entry,
        scope=context.scope,
        reachability=reachability,
        cardinality=cardinality,
        effect_trace=effect_trace,
        completion=completion,
        unknown_reasons=reasons,
    )


def edge_evidence_from_analysis(
    analysis: AbstractAnalysisResult,
    context: AbstractEvidenceContext,
    *,
    synthesized_failure: bool = False,
) -> EdgeExecutionEvidence:
    item = context_evidence_from_analysis(analysis, context)
    approximation = Approximation.combine(
        (
            item.reachability.approximation,
            item.cardinality.approximation,
            item.effect_trace.approximation,
            item.completion.approximation,
        )
    )
    return EdgeExecutionEvidence(
        edge_id=context.edge_id,
        synthesized_failure=synthesized_failure,
        contexts=(item,),
        completion=item.completion,
        approximation=approximation,
    )


def _reachability(
    analysis: AbstractAnalysisResult,
    relevant: Sequence[GuardedAlternative],
    context: AbstractEvidenceContext,
) -> ReachabilityEvidence:
    precondition = _precondition(relevant)
    if not relevant:
        exact = (
            analysis.approximation.is_exact
            and all(not item.transition_trace_top for item in analysis.completed)
        )
        if exact:
            return ReachabilityEvidence(
                ReachabilityStatus.PROVEN_UNREACHABLE,
                None,
                None,
                _exact(
                    ExactnessProofScope.REACHABILITY,
                    f"exact abstract execution contains no edge {context.source_edge_id}",
                ),
            )
        return ReachabilityEvidence(
            ReachabilityStatus.UNKNOWN,
            None,
            None,
            Approximation.unknown("abstract-reachability-incomplete"),
        )

    witness = context.witness
    if witness is not None and witness.edge_id == context.source_edge_id:
        witness_ir = witness.to_ir()
        witness_ir["edge_id"] = context.edge_id
        witness_ir["analysis_edge_id"] = context.source_edge_id
        return ReachabilityEvidence(
            ReachabilityStatus.PROVEN_REACHABLE,
            precondition,
            witness_ir,
            _exact(
                ExactnessProofScope.REACHABILITY,
                f"concrete TEIR replay traversed edge {context.source_edge_id}",
                kind=ExactnessProofKind.CONCRETE_REPLAY,
            ),
        )

    return ReachabilityEvidence(
        ReachabilityStatus.MAY_REACHABLE,
        precondition,
        None,
        Approximation.over_approximate("reachability-witness-missing"),
    )


def _cardinality(
    analysis: AbstractAnalysisResult,
    relevant: Sequence[GuardedAlternative],
    edge_id: str,
) -> CallCardinalityEvidence:
    if any(item.transition_trace_top for item in analysis.completed):
        return CallCardinalityEvidence(
            CallUpperBound.UNKNOWN,
            None,
            Approximation.unknown("transition-trace-top"),
        )
    counts = tuple(
        sum(event.edge_id == edge_id for event in item.transition_trace)
        for item in analysis.completed
    )
    maximum = max(counts, default=0)
    upper_bound = (
        CallUpperBound.ZERO
        if maximum == 0
        else CallUpperBound.AT_MOST_ONE
        if maximum == 1
        else CallUpperBound.MANY
    )
    if analysis.approximation.is_exact:
        approximation = _exact(
            ExactnessProofScope.CARDINALITY,
            f"complete abstract traces bound edge {edge_id} by {upper_bound.value}",
        )
    else:
        approximation = Approximation.over_approximate(
            *(analysis.approximation.causes or ("analysis-cardinality-incomplete",))
        )
    return CallCardinalityEvidence(upper_bound, None, approximation)


def _effect_trace(
    analysis: AbstractAnalysisResult,
    relevant: Sequence[GuardedAlternative],
) -> EffectTraceEvidence:
    if not relevant:
        approximation = (
            _exact(ExactnessProofScope.EFFECT_TRACE, "unreachable edge has no effect trace")
            if analysis.approximation.is_exact
            else Approximation.unknown("effect-trace-unreachable-or-incomplete")
        )
        return EffectTraceEvidence((), approximation)
    if any(item.effect_trace_top for item in relevant):
        return EffectTraceEvidence(
            tuple(_trace_alternative(item) for item in relevant),
            Approximation.unknown("effect-trace-top"),
        )

    alternatives = tuple(_trace_alternative(item) for item in relevant)
    event_sequences = {alternative.events for alternative in alternatives}
    if len(event_sequences) == 1:
        normalized = (TraceAlternative(None, next(iter(event_sequences))),)
    else:
        normalized = _deduplicate_trace_alternatives(alternatives)

    exact = analysis.approximation.is_exact and all(
        item.approximation.is_exact for item in relevant
    )
    approximation = (
        _exact(
            ExactnessProofScope.EFFECT_TRACE,
            "path-partitioned abstract execution preserves complete effect traces",
        )
        if exact
        else Approximation.over_approximate(
            *(analysis.approximation.causes or ("effect-trace-analysis-incomplete",))
        )
    )
    return EffectTraceEvidence(normalized, approximation)


def _completion(
    analysis: AbstractAnalysisResult,
    relevant: Sequence[GuardedAlternative],
) -> CompletionEvidence:
    if not relevant:
        return CompletionEvidence(
            (CompletionKind.NO_CONTINUATION,),
            (
                _exact(
                    ExactnessProofScope.COMPLETION,
                    "unreachable edge has no caller continuation",
                )
                if analysis.approximation.is_exact
                else Approximation.unknown("completion-unreachable-or-incomplete")
            ),
        )

    kinds = tuple(
        _completion_kind(kind)
        for alternative in relevant
        for kind in alternative.completion
        if kind != "running"
    ) or (CompletionKind.UNKNOWN,)
    exact = analysis.approximation.is_exact and all(
        item.approximation.is_exact for item in relevant
    )
    approximation = (
        _exact(
            ExactnessProofScope.COMPLETION,
            "complete abstract alternatives preserve terminal completion kinds",
        )
        if exact
        else Approximation.over_approximate(
            *(analysis.approximation.causes or ("completion-analysis-incomplete",))
        )
    )
    return CompletionEvidence(kinds, approximation)


def _trace_alternative(alternative: GuardedAlternative) -> TraceAlternative:
    condition = (
        None
        if isinstance(alternative.path_condition, BoolExpr)
        and alternative.path_condition.value
        else repr(alternative.path_condition)
    )
    return TraceAlternative(
        condition,
        tuple(
            EffectEvent(
                operation=event.operation,
                expression=(
                    f"{event.operation}("
                    + ", ".join(repr(argument) for argument in event.arguments)
                    + ")"
                ),
            )
            for event in alternative.effect_trace
        ),
    )


def _deduplicate_trace_alternatives(
    alternatives: Sequence[TraceAlternative],
) -> tuple[TraceAlternative, ...]:
    result: list[TraceAlternative] = []
    for alternative in alternatives:
        if alternative not in result:
            result.append(alternative)
    return tuple(result)


def _precondition(relevant: Sequence[GuardedAlternative]) -> str | None:
    values = tuple(dict.fromkeys(repr(item.path_condition) for item in relevant))
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return " | ".join(f"({value})" for value in values)


def _completion_kind(value: str) -> CompletionKind:
    return {
        "returned": CompletionKind.NORMAL,
        "normal": CompletionKind.NORMAL,
        "propagated-failure": CompletionKind.PROPAGATED_FAILURE,
        "terminated": CompletionKind.TERMINATED,
        "diverged": CompletionKind.DIVERGED,
        "no-continuation": CompletionKind.NO_CONTINUATION,
    }.get(value, CompletionKind.UNKNOWN)


def _exact(
    scope: ExactnessProofScope,
    detail: str,
    *,
    kind: ExactnessProofKind = ExactnessProofKind.STRUCTURAL_IDENTITY,
) -> Approximation:
    return Approximation.exact(ExactnessProof(kind, scope, detail))

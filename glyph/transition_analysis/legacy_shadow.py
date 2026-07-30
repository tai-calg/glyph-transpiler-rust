from __future__ import annotations

from copy import deepcopy
from typing import Mapping, Sequence

from .evidence import (
    CallCardinalityEvidence,
    CallUpperBound,
    CompletionEvidence,
    CompletionKind,
    ContextExecutionEvidence,
    EdgeExecutionEvidence,
    EffectTraceEvidence,
    ReachabilityEvidence,
    ReachabilityStatus,
    TraceAlternative,
    effect_events,
)
from .exactness import Approximation, ApproximationCause
from .projection import check_exact_action_projection


LEGACY_SHADOW_VERSION = 1


def attach_execution_evidence_v2(
    machine_view: dict[str, object],
) -> dict[str, object]:
    """現行解析をEvidence v2へ保守的に写像するshadow pass。

    現行`resolved`はExactの証明ではないため、legacy adapter由来のEvidenceを
    確定表示へ昇格させない。既存UIの挙動は変更せず、比較・監査用Evidenceだけを
    追加する。
    """

    result = deepcopy(machine_view)
    transitions: list[dict[str, object]] = []
    context_count = 0
    rejected_projection_count = 0
    unknown_context_count = 0

    for index, original in enumerate(result.get("transitions", [])):
        transition = dict(original)
        synthesized_failure = bool(transition.get("synthesized_failure"))
        edge_id = _edge_id(transition, index)
        contexts = tuple(
            _context_evidence(edge_id, binding)
            for binding in _mappings(
                transition.get("execution_action_bindings")
                or transition.get("execution_contexts")
                or []
            )
        )
        context_count += len(contexts)
        unknown_context_count += sum(
            1
            for context in contexts
            if context.reachability.status is ReachabilityStatus.UNKNOWN
        )

        if synthesized_failure:
            edge_completion = CompletionEvidence(
                (CompletionKind.NO_CONTINUATION,),
                Approximation.over_approximate(ApproximationCause.LEGACY_ADAPTER),
            )
        elif contexts:
            edge_completion = CompletionEvidence(
                tuple(
                    kind
                    for context in contexts
                    for kind in context.completion.kinds
                ),
                Approximation.combine(
                    context.completion.approximation for context in contexts
                ),
            )
        else:
            edge_completion = CompletionEvidence(
                (CompletionKind.UNKNOWN,),
                Approximation.unknown(ApproximationCause.LEGACY_UNRESOLVED),
            )

        if contexts:
            edge_approximation = Approximation.combine(
                _context_approximations(contexts)
            )
        elif synthesized_failure:
            edge_approximation = Approximation.over_approximate(
                ApproximationCause.LEGACY_ADAPTER
            )
        else:
            edge_approximation = Approximation.unknown(
                ApproximationCause.LEGACY_UNRESOLVED
            )
        evidence = EdgeExecutionEvidence(
            edge_id=edge_id,
            synthesized_failure=synthesized_failure,
            contexts=contexts,
            completion=edge_completion,
            approximation=edge_approximation,
        ).to_ir()

        projections: list[dict[str, object]] = []
        for context in evidence["contexts"]:
            if not isinstance(context, Mapping):
                continue
            decision = check_exact_action_projection(context)
            if not decision.allowed:
                rejected_projection_count += 1
            projections.append(decision.to_ir())
        evidence["exact_action_projection_checks"] = projections
        evidence["shadow_version"] = LEGACY_SHADOW_VERSION
        transition["execution_evidence_v2"] = evidence
        transitions.append(transition)

    analysis = dict(result.get("analysis", {}))
    analysis.update(
        {
            "execution_evidence_v2_version": 2,
            "execution_evidence_v2_shadow_version": LEGACY_SHADOW_VERSION,
            "execution_evidence_v2_context_count": context_count,
            "execution_evidence_v2_unknown_context_count": unknown_context_count,
            "execution_evidence_v2_rejected_exact_projection_count": (
                rejected_projection_count
            ),
            "execution_evidence_v2_is_projection_source": False,
        }
    )
    result["transitions"] = transitions
    result["analysis"] = analysis
    return result


def _context_evidence(
    edge_id: str,
    binding: Mapping[str, object],
) -> ContextExecutionEvidence:
    status = str(binding.get("status") or "unresolved")
    count = _integer(binding.get("transition_call_count"))
    approximation = (
        Approximation.unknown(ApproximationCause.LEGACY_UNRESOLVED)
        if status == "unresolved"
        else Approximation.over_approximate(ApproximationCause.LEGACY_ADAPTER)
    )
    reachability = ReachabilityEvidence(
        status=(
            ReachabilityStatus.UNKNOWN
            if status == "unresolved"
            else ReachabilityStatus.MAY_REACHABLE
        ),
        precondition=_context_precondition(binding),
        witness=None,
        approximation=approximation,
    )
    cardinality = CallCardinalityEvidence(
        upper_bound=_cardinality(status, count),
        witness=None,
        approximation=approximation,
    )
    trace = EffectTraceEvidence(
        alternatives=_trace_alternatives(binding),
        approximation=approximation,
    )
    completion = CompletionEvidence(
        _completion_kinds(binding),
        approximation,
    )
    reasons = [ApproximationCause.LEGACY_ADAPTER.value]
    if status == "unresolved":
        reasons.append(ApproximationCause.LEGACY_UNRESOLVED.value)
    if status == "multiple-transition-calls":
        reasons.append("multiple-transition-calls")
    action = binding.get("action")
    return ContextExecutionEvidence(
        edge_id=edge_id,
        system=_optional_text(binding.get("system")),
        entry=str(binding.get("entry") or ""),
        scope=str(binding.get("scope") or "system"),
        reachability=reachability,
        cardinality=cardinality,
        effect_trace=trace,
        completion=completion,
        unknown_reasons=tuple(sorted(set(reasons))),
        legacy_projection=dict(action) if isinstance(action, Mapping) else None,
    )


def _trace_alternatives(
    binding: Mapping[str, object],
) -> tuple[TraceAlternative, ...]:
    cases = _mappings(binding.get("action_cases") or [])
    if cases:
        return tuple(
            TraceAlternative(
                condition=_optional_text(case.get("condition")),
                events=effect_events(
                    _mappings(
                        case.get("effect_invocations")
                        or case.get("action_invocations")
                        or []
                    )
                ),
            )
            for case in cases
        )
    return (
        TraceAlternative(
            condition=None,
            events=effect_events(
                _mappings(
                    binding.get("effect_invocations")
                    or binding.get("action_invocations")
                    or []
                )
            ),
        ),
    )


def _completion_kinds(binding: Mapping[str, object]) -> tuple[CompletionKind, ...]:
    cases = _mappings(binding.get("action_cases") or [])
    if not cases:
        return (CompletionKind.UNKNOWN,) if binding.get("status") == "unresolved" else (
            CompletionKind.NORMAL,
        )
    kinds: list[CompletionKind] = []
    for case in cases:
        outcome = str(case.get("outcome") or "success")
        reaches = case.get("reaches_continuation") is not False
        if outcome == "failure-return":
            kinds.append(CompletionKind.PROPAGATED_FAILURE)
        elif not reaches:
            kinds.append(CompletionKind.NO_CONTINUATION)
        else:
            kinds.append(CompletionKind.NORMAL)
    return tuple(kinds) or (CompletionKind.UNKNOWN,)


def _cardinality(status: str, count: int) -> CallUpperBound:
    if status == "unresolved":
        return CallUpperBound.UNKNOWN
    if status == "multiple-transition-calls" or count > 1:
        return CallUpperBound.MANY
    if count <= 0:
        return CallUpperBound.ZERO
    return CallUpperBound.AT_MOST_ONE


def _context_precondition(binding: Mapping[str, object]) -> str | None:
    conditions = [
        str(case.get("condition"))
        for case in _mappings(binding.get("action_cases") or [])
        if case.get("condition")
    ]
    if not conditions:
        return None
    return " | ".join(f"({condition})" for condition in conditions)


def _context_approximations(
    contexts: Sequence[ContextExecutionEvidence],
) -> tuple[Approximation, ...]:
    return tuple(
        Approximation.combine(
            (
                context.reachability.approximation,
                context.cardinality.approximation,
                context.effect_trace.approximation,
                context.completion.approximation,
            )
        )
        for context in contexts
    )


def _edge_id(transition: Mapping[str, object], index: int) -> str:
    explicit = transition.get("id") or transition.get("edge_id")
    if explicit:
        return str(explicit)
    source = str(transition.get("source_state") or "?")
    target = str(transition.get("target_state") or transition.get("target") or "?")
    line = transition.get("source")
    if isinstance(line, Mapping):
        line = line.get("line")
    return f"{source}->{target}@{line or index + 1}"


def _mappings(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _integer(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional_text(value: object) -> str | None:
    text = str(value) if value is not None else ""
    return text or None

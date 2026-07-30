from __future__ import annotations

from copy import deepcopy
from typing import Mapping, Sequence

from ..artifacts import CompilationModel
from .analysis_evidence import (
    ABSTRACT_EVIDENCE_ADAPTER_VERSION,
    AbstractEvidenceContext,
    context_evidence_from_analysis,
)
from .effect_contract import (
    EFFECT_CONTRACT_REGISTRY_VERSION,
    VerifiedEffectContractRegistry,
)
from .evidence import (
    CompletionEvidence,
    CompletionKind,
    ContextExecutionEvidence,
    EdgeExecutionEvidence,
)
from .exactness import Approximation
from .machine_relation import build_machine_relation
from .projection import check_exact_action_projection
from .summary_interpreter import SummaryAwareAbstractInterpreter
from .view_edge_specialization import ViewEdgeBindingStatus
from .witness_generation import (
    BoundedWitnessGenerationReport,
    WITNESS_GENERATION_VERSION,
    disabled_witness_generation_ir,
    generate_bounded_system_witnesses,
)


RTAI_ABSTRACT_EVIDENCE_SHADOW_VERSION = 2


def attach_rtai_abstract_execution_evidence(
    model: CompilationModel,
    machine_view: dict[str, object],
    *,
    effect_contracts: VerifiedEffectContractRegistry | None = None,
    witness_max_cases: int = 4096,
) -> dict[str, object]:
    """Attach native RTAI Evidence without replacing legacy UI projection.

    The machine-level contract remains keyed by normalized MachineRelation edges.
    When a rendered transition has an exact specialization binding, an additional
    view-edge Evidence record is attached directly to that transition. Normal and
    synthesized-failure transitions use disjoint completion partitions.

    Automatic concrete witnesses are generated only when an explicit verified
    Effect-contract registry is supplied.  Missing contracts never fall back to an
    inferred handler.
    """

    result = deepcopy(machine_view)
    machine_name = str(result.get("name") or "")
    relation = build_machine_relation(model, machine_name)
    issues: list[dict[str, str]] = []
    edges: list[dict[str, object]] = []
    view_edges: list[dict[str, object]] = []
    analyzed_entries = 0
    relation_context_count = 0
    view_context_count = 0
    exact_projection_count = 0

    analyses = {}
    systems_by_entry: dict[str, list[str]] = {}
    witness_report: BoundedWitnessGenerationReport | None = None
    if relation is not None:
        analyzer = SummaryAwareAbstractInterpreter(
            model,
            contextual_effect_summaries=(
                effect_contracts.abstract_registry()
                if effect_contracts is not None
                else None
            ),
        )
        for system in model.systems:
            systems_by_entry.setdefault(system.entry_name, []).append(system.name)

        if effect_contracts is not None:
            witness_report = generate_bounded_system_witnesses(
                model,
                systems_by_entry,
                effect_contracts,
                max_cases_per_entry=witness_max_cases,
            )
            issues.extend(
                {
                    "entry": item.entry,
                    "reason": f"{item.code}: {item.detail}",
                }
                for item in witness_report.issues
            )

        for entry in sorted(systems_by_entry):
            if entry not in analyzer.functions:
                issues.append(
                    {
                        "entry": entry,
                        "reason": "TEIR entry is unavailable",
                    }
                )
                continue
            try:
                analyses[entry] = analyzer.analyze(entry)
                analyzed_entries += 1
            except (KeyError, RuntimeError, TypeError, ValueError) as error:
                issues.append(
                    {
                        "entry": entry,
                        "reason": str(error) or type(error).__name__,
                    }
                )

        for edge in relation.edges:
            contexts = _contexts_for_edge(
                analyses,
                systems_by_entry,
                output_edge_id=edge.edge_id,
                analysis_edge_id=edge.edge_id,
                completion_filter=None,
                witness_report=witness_report,
            )
            relation_context_count += len(contexts)
            evidence = _edge_evidence(
                edge.edge_id,
                contexts,
                synthesized_failure=False,
            )
            checks = _projection_checks(evidence)
            exact_projection_count += sum(bool(item["allowed"]) for item in checks)
            evidence["exact_action_projection_checks"] = checks
            edges.append(evidence)

    transitions: list[dict[str, object]] = []
    for index, original in enumerate(_mappings(result.get("transitions"))):
        transition = dict(original)
        view_edge_id = str(
            transition.get("id")
            or transition.get("edge_id")
            or f"T{index + 1}"
        )
        binding = _mapping(transition.get("rtai_view_edge_specialization"))
        relation_edge_id = str(binding.get("relation_edge_id") or "")
        status = str(binding.get("status") or "unmapped")
        synthesized_failure = bool(transition.get("synthesized_failure"))

        if relation_edge_id and status in {
            ViewEdgeBindingStatus.EXACT.value,
            ViewEdgeBindingStatus.SYNTHESIZED_FAILURE.value,
        }:
            completion_filter = (
                frozenset({"propagated-failure"})
                if synthesized_failure
                else frozenset({"returned", "normal"})
            )
            contexts = _contexts_for_edge(
                analyses,
                systems_by_entry,
                output_edge_id=view_edge_id,
                analysis_edge_id=relation_edge_id,
                completion_filter=completion_filter,
                witness_report=witness_report,
            )
            view_context_count += len(contexts)
            evidence = _edge_evidence(
                view_edge_id,
                contexts,
                synthesized_failure=synthesized_failure,
            )
        else:
            evidence = _unmapped_view_evidence(
                view_edge_id,
                synthesized_failure=synthesized_failure,
                reason=f"view-edge-specialization-{status}",
            )

        evidence["analysis_edge_id"] = relation_edge_id or None
        evidence["view_edge_specialization_status"] = status
        checks = _projection_checks(evidence)
        exact_projection_count += sum(bool(item["allowed"]) for item in checks)
        evidence["exact_action_projection_checks"] = checks
        transition["rtai_execution_evidence_v2"] = evidence
        transitions.append(transition)
        view_edges.append(evidence)

    payload = {
        "version": RTAI_ABSTRACT_EVIDENCE_SHADOW_VERSION,
        "adapter_version": ABSTRACT_EVIDENCE_ADAPTER_VERSION,
        "projection_source": False,
        "machine_relation": relation.to_ir() if relation is not None else None,
        "effect_contracts": (
            effect_contracts.to_ir()
            if effect_contracts is not None
            else {
                "version": EFFECT_CONTRACT_REGISTRY_VERSION,
                "configured": False,
                "defaults": [],
                "by_entry": [],
            }
        ),
        "witness_generation": (
            witness_report.to_ir()
            if witness_report is not None
            else disabled_witness_generation_ir()
        ),
        "edges": edges,
        "view_edges": view_edges,
        "issues": issues,
    }
    analysis = dict(result.get("analysis", {}))
    analysis.update(
        {
            "rtai_abstract_execution_evidence_version": (
                RTAI_ABSTRACT_EVIDENCE_SHADOW_VERSION
            ),
            "rtai_abstract_execution_evidence_is_projection_source": False,
            "rtai_abstract_execution_evidence_edge_count": len(edges),
            "rtai_abstract_execution_view_edge_count": len(view_edges),
            "rtai_abstract_execution_evidence_context_count": (
                relation_context_count
            ),
            "rtai_abstract_execution_view_context_count": view_context_count,
            "rtai_abstract_execution_analyzed_entry_count": analyzed_entries,
            "rtai_abstract_execution_issue_count": len(issues),
            "rtai_abstract_execution_exact_projection_count": exact_projection_count,
            "rtai_effect_contract_registry_version": (
                EFFECT_CONTRACT_REGISTRY_VERSION
            ),
            "rtai_effect_contracts_configured": effect_contracts is not None,
            "rtai_witness_generation_version": WITNESS_GENERATION_VERSION,
            "rtai_witness_generation_enabled": witness_report is not None,
            "rtai_witness_generation_complete": (
                witness_report.complete if witness_report is not None else False
            ),
            "rtai_generated_witness_count": (
                len(witness_report.witnesses) if witness_report is not None else 0
            ),
        }
    )
    result["transitions"] = transitions
    result["rtai_abstract_execution_evidence_v2"] = payload
    result["analysis"] = analysis
    return result


def _contexts_for_edge(
    analyses: Mapping[str, object],
    systems_by_entry: Mapping[str, Sequence[str]],
    *,
    output_edge_id: str,
    analysis_edge_id: str,
    completion_filter: frozenset[str] | None,
    witness_report: BoundedWitnessGenerationReport | None,
) -> tuple[ContextExecutionEvidence, ...]:
    contexts: list[ContextExecutionEvidence] = []
    for entry, raw_analysis in analyses.items():
        witness = (
            witness_report.witness_for(
                entry,
                analysis_edge_id,
                completion_filter,
            )
            if witness_report is not None
            else None
        )
        for system_name in systems_by_entry.get(entry, ()):
            contexts.append(
                context_evidence_from_analysis(
                    raw_analysis,  # type: ignore[arg-type]
                    AbstractEvidenceContext(
                        output_edge_id,
                        system_name,
                        entry,
                        witness=witness,
                        analysis_edge_id=analysis_edge_id,
                        completion_filter=completion_filter,
                    ),
                )
            )
    return tuple(contexts)


def _edge_evidence(
    edge_id: str,
    contexts: Sequence[ContextExecutionEvidence],
    *,
    synthesized_failure: bool,
) -> dict[str, object]:
    if contexts:
        completion = CompletionEvidence(
            tuple(
                kind
                for context in contexts
                for kind in context.completion.kinds
            ),
            Approximation.combine(
                context.completion.approximation for context in contexts
            ),
        )
        approximation = Approximation.combine(
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
    else:
        completion = CompletionEvidence(
            (CompletionKind.UNKNOWN,),
            Approximation.unknown("rtai-system-entry-analysis-unavailable"),
        )
        approximation = Approximation.unknown(
            "rtai-system-entry-analysis-unavailable"
        )
    return EdgeExecutionEvidence(
        edge_id=edge_id,
        synthesized_failure=synthesized_failure,
        contexts=tuple(contexts),
        completion=completion,
        approximation=approximation,
    ).to_ir()


def _unmapped_view_evidence(
    edge_id: str,
    *,
    synthesized_failure: bool,
    reason: str,
) -> dict[str, object]:
    completion = CompletionEvidence(
        (CompletionKind.UNKNOWN,),
        Approximation.unknown(reason),
    )
    return EdgeExecutionEvidence(
        edge_id=edge_id,
        synthesized_failure=synthesized_failure,
        contexts=(),
        completion=completion,
        approximation=Approximation.unknown(reason),
    ).to_ir()


def _projection_checks(evidence: Mapping[str, object]) -> list[dict[str, object]]:
    return [
        check_exact_action_projection(context).to_ir()
        for context in _mappings(evidence.get("contexts"))
    ]


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mappings(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))

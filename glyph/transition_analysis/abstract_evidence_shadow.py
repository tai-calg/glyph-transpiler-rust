from __future__ import annotations

from copy import deepcopy

from ..artifacts import CompilationModel
from .analysis_evidence import (
    ABSTRACT_EVIDENCE_ADAPTER_VERSION,
    AbstractEvidenceContext,
    context_evidence_from_analysis,
)
from .evidence import (
    CompletionEvidence,
    CompletionKind,
    EdgeExecutionEvidence,
)
from .exactness import Approximation
from .machine_relation import build_machine_relation
from .projection import check_exact_action_projection
from .summary_interpreter import SummaryAwareAbstractInterpreter


RTAI_ABSTRACT_EVIDENCE_SHADOW_VERSION = 1


def attach_rtai_abstract_execution_evidence(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Attach native RTAI Evidence without replacing legacy UI projection.

    Evidence is keyed by normalized MachineRelation edge identity.  It remains a
    parallel contract until bounded witness replay and view-edge specialization
    provide the exact reachability proof needed by the projection checker.
    """

    result = deepcopy(machine_view)
    machine_name = str(result.get("name") or "")
    relation = build_machine_relation(model, machine_name)
    issues: list[dict[str, str]] = []
    edges: list[dict[str, object]] = []
    analyzed_entries = 0
    context_count = 0
    exact_projection_count = 0

    if relation is not None:
        analyzer = SummaryAwareAbstractInterpreter(model)
        analyses = {}
        systems_by_entry: dict[str, list[str]] = {}
        for system in model.systems:
            systems_by_entry.setdefault(system.entry_name, []).append(system.name)
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
            contexts = []
            for entry, analysis in analyses.items():
                for system_name in systems_by_entry.get(entry, ()):
                    context = context_evidence_from_analysis(
                        analysis,
                        AbstractEvidenceContext(
                            edge.edge_id,
                            system_name,
                            entry,
                        ),
                    )
                    contexts.append(context)
                    context_count += 1

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

            evidence = EdgeExecutionEvidence(
                edge_id=edge.edge_id,
                synthesized_failure=False,
                contexts=tuple(contexts),
                completion=completion,
                approximation=approximation,
            ).to_ir()
            checks = [
                check_exact_action_projection(context).to_ir()
                for context in evidence["contexts"]
                if isinstance(context, dict)
            ]
            exact_projection_count += sum(bool(item["allowed"]) for item in checks)
            evidence["exact_action_projection_checks"] = checks
            edges.append(evidence)

    payload = {
        "version": RTAI_ABSTRACT_EVIDENCE_SHADOW_VERSION,
        "adapter_version": ABSTRACT_EVIDENCE_ADAPTER_VERSION,
        "projection_source": False,
        "machine_relation": relation.to_ir() if relation is not None else None,
        "edges": edges,
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
            "rtai_abstract_execution_evidence_context_count": context_count,
            "rtai_abstract_execution_analyzed_entry_count": analyzed_entries,
            "rtai_abstract_execution_issue_count": len(issues),
            "rtai_abstract_execution_exact_projection_count": exact_projection_count,
        }
    )
    result["rtai_abstract_execution_evidence_v2"] = payload
    result["analysis"] = analysis
    return result

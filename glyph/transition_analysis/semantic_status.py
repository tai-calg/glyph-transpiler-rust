from __future__ import annotations

from copy import deepcopy
from typing import Mapping, Sequence

from .evidence_projection import audit_evidence_projection


RTAI_SEMANTIC_STATUS_VERSION = 1


def attach_rtai_semantic_status(
    machine_view: Mapping[str, object],
) -> dict[str, object]:
    """Publish a presentation-ready Exact / May / Unknown classification.

    This pass does not re-run AST, CFG or solver semantics. It classifies only the
    native Evidence and readiness report already present on the rendered edge.
    """

    result = deepcopy(dict(machine_view))
    report = audit_evidence_projection(
        result,
        evidence_field="rtai_execution_evidence_v2",
        include_empty_evidence=True,
    )
    readiness = {item.edge_id: item for item in report.transitions}
    transitions: list[dict[str, object]] = []
    counts = {"exact": 0, "may": 0, "unknown": 0}

    for index, original in enumerate(_mappings(result.get("transitions"))):
        transition = dict(original)
        evidence = _mapping(transition.get("rtai_execution_evidence_v2"))
        edge_id = str(
            evidence.get("edge_id")
            or transition.get("id")
            or transition.get("edge_id")
            or index
        )
        item = readiness.get(edge_id)
        status, reason = _classify(evidence, item)
        counts[status] += 1
        transition["rtai_semantic_status"] = {
            "version": RTAI_SEMANTIC_STATUS_VERSION,
            "status": status,
            "reason": reason,
            "context_count": len(_mappings(evidence.get("contexts"))),
            "projection_ready": bool(item.ready) if item is not None else False,
        }
        transitions.append(transition)

    analysis = dict(_mapping(result.get("analysis")))
    analysis.update(
        {
            "rtai_semantic_status_version": RTAI_SEMANTIC_STATUS_VERSION,
            "rtai_semantic_exact_transition_count": counts["exact"],
            "rtai_semantic_may_transition_count": counts["may"],
            "rtai_semantic_unknown_transition_count": counts["unknown"],
        }
    )
    result["transitions"] = transitions
    result["analysis"] = analysis
    return result


def _classify(
    evidence: Mapping[str, object],
    readiness: object | None,
) -> tuple[str, str]:
    if readiness is not None and bool(getattr(readiness, "ready", False)):
        return "exact", str(getattr(readiness, "reason", "exact-evidence"))

    contexts = _mappings(evidence.get("contexts"))
    if not evidence or not contexts:
        return "unknown", "native-evidence-context-is-missing"
    if str(evidence.get("view_edge_specialization_status") or "") not in {
        "exact",
        "synthesized-failure",
    }:
        return "unknown", "rendered-edge-specialization-is-unresolved"

    for context in contexts:
        if context.get("unknown_reasons"):
            return "unknown", "native-evidence-has-unknown-reasons"
        reachability = _mapping(context.get("reachability"))
        if reachability.get("status") == "unknown":
            return "unknown", "reachability-is-unknown"
        for field in ("reachability", "cardinality", "effect_trace", "completion"):
            approximation = _mapping(_mapping(context.get(field)).get("approximation"))
            if approximation.get("kind") == "unknown":
                return "unknown", f"{field.replace('_', '-')}-is-unknown"

    reason = (
        str(getattr(readiness, "reason", ""))
        if readiness is not None
        else "exact-projection-is-not-proven"
    )
    return "may", reason or "exact-projection-is-not-proven"


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mappings(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


__all__ = [
    "RTAI_SEMANTIC_STATUS_VERSION",
    "attach_rtai_semantic_status",
]

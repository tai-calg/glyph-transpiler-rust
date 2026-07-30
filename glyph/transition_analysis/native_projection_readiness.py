from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from .evidence_projection import audit_evidence_projection


NATIVE_EVIDENCE_READINESS_VERSION = 1


def attach_native_evidence_projection_readiness(
    machine_view: Mapping[str, object],
) -> dict[str, object]:
    result = deepcopy(dict(machine_view))
    report = audit_evidence_projection(
        result,
        evidence_field="rtai_execution_evidence_v2",
        include_empty_evidence=True,
    )
    analysis = dict(
        result.get("analysis")
        if isinstance(result.get("analysis"), Mapping)
        else {}
    )
    analysis.update(
        {
            "rtai_native_evidence_readiness_version": (
                NATIVE_EVIDENCE_READINESS_VERSION
            ),
            "rtai_native_evidence_projection_ready": report.ready,
            "rtai_native_evidence_relevant_transition_count": (
                report.relevant_transition_count
            ),
            "rtai_native_evidence_ready_transition_count": (
                report.ready_transition_count
            ),
            "rtai_native_evidence_rejected_context_count": (
                report.rejected_context_count
            ),
        }
    )
    result["rtai_native_evidence_projection_readiness"] = report.to_ir()
    result["analysis"] = analysis
    return result

from __future__ import annotations

from copy import deepcopy
from typing import Mapping, Sequence

from ..artifacts import CompilationModel
from .abstract_evidence_shadow import attach_rtai_abstract_execution_evidence
from .effect_contract import VerifiedEffectContractRegistry
from .evidence_projection import EvidenceProjectionMode, project_machine_from_evidence
from .native_projection_readiness import attach_native_evidence_projection_readiness
from .view_edge_specialization import attach_view_edge_specialization


STRICT_PROJECTION_CAMPAIGN_VERSION = 1


def build_strict_projection_candidate(
    model: CompilationModel,
    machine_view: Mapping[str, object],
    effect_contracts: VerifiedEffectContractRegistry,
    *,
    witness_max_cases: int = 4096,
) -> dict[str, object]:
    """Build a fail-closed native-Evidence projection candidate.

    This API is intentionally separate from the normal compiler pipeline.  It
    disables legacy System Action fallback for every rendered transition, retains
    Machine-owned actions, and publishes an explicit campaign report.  An unready
    edge receives no strict System Action instead of borrowing legacy output.
    """

    specialized = attach_view_edge_specialization(model, dict(machine_view))
    evidenced = attach_rtai_abstract_execution_evidence(
        model,
        specialized,
        effect_contracts=effect_contracts,
        witness_max_cases=witness_max_cases,
    )
    readiness = attach_native_evidence_projection_readiness(evidenced)
    projected = project_machine_from_evidence(
        readiness,
        mode=EvidenceProjectionMode.STRICT_EXACT,
        evidence_field="rtai_execution_evidence_v2",
    )

    result = deepcopy(projected)
    transitions: list[dict[str, object]] = []
    for original in _mappings(result.get("transitions")):
        transition = dict(original)
        transition["legacy_system_action_fallback_allowed"] = False
        transition["strict_system_action"] = transition.get("evidence_display_action")
        transition["strict_system_action_projection_source"] = (
            "rtai-execution-evidence-v2"
        )
        _remove_legacy_system_projection(transition)
        transitions.append(transition)

    native_report = _mapping(
        result.get("rtai_native_evidence_projection_readiness")
    )
    evidence_payload = _mapping(result.get("rtai_abstract_execution_evidence_v2"))
    witness_report = _mapping(evidence_payload.get("witness_generation"))
    ready = bool(native_report.get("ready")) and bool(
        witness_report.get("complete")
    )
    blockers = _campaign_blockers(native_report, witness_report)

    analysis = dict(_mapping(result.get("analysis")))
    analysis.update(
        {
            "rtai_strict_projection_campaign_version": (
                STRICT_PROJECTION_CAMPAIGN_VERSION
            ),
            "rtai_strict_projection_campaign_ready": ready,
            "rtai_strict_projection_legacy_fallback_enabled": False,
            "rtai_strict_projection_blocker_count": len(blockers),
        }
    )
    result["transitions"] = transitions
    result["strict_projection_campaign"] = {
        "version": STRICT_PROJECTION_CAMPAIGN_VERSION,
        "ready": ready,
        "projection_source": "rtai-execution-evidence-v2",
        "legacy_fallback_allowed": False,
        "witness_generation_complete": bool(witness_report.get("complete")),
        "blockers": blockers,
    }
    result["analysis"] = analysis
    return result


def _remove_legacy_system_projection(transition: dict[str, object]) -> None:
    """Remove legacy System-only projections without touching Machine actions."""

    transition["execution_action_bindings"] = []
    transition["execution_contexts"] = []
    transition["system_execution_actions"] = []
    transition["system_action"] = None
    transition["system_actions"] = []


def _campaign_blockers(
    native_report: Mapping[str, object],
    witness_report: Mapping[str, object],
) -> list[dict[str, object]]:
    blockers: list[dict[str, object]] = []
    for item in _mappings(native_report.get("transitions")):
        if item.get("ready") is True:
            continue
        blockers.append(
            {
                "kind": "transition-not-ready",
                "edge_id": item.get("edge_id"),
                "reason": item.get("reason"),
            }
        )
    for item in _mappings(witness_report.get("issues")):
        blockers.append(
            {
                "kind": "witness-generation",
                "entry": item.get("entry"),
                "reason": item.get("code"),
                "detail": item.get("detail"),
            }
        )
    if not witness_report.get("enabled"):
        blockers.append(
            {
                "kind": "witness-generation",
                "reason": "witness-generation-disabled",
            }
        )
    return blockers


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mappings(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


__all__ = [
    "STRICT_PROJECTION_CAMPAIGN_VERSION",
    "build_strict_projection_candidate",
]

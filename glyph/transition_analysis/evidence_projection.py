from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
import json
from typing import Mapping, Sequence

from .projection import ExactActionDecision, check_exact_action_projection


EVIDENCE_PROJECTION_VERSION = 2


class EvidenceProjectionMode(str, Enum):
    SHADOW = "shadow"
    PREFER_EXACT = "prefer-exact"
    STRICT_EXACT = "strict-exact"


@dataclass(frozen=True)
class TransitionProjectionReadiness:
    edge_id: str
    context_count: int
    exact_context_count: int
    ready: bool
    reason: str
    action: Mapping[str, object] | None

    def to_ir(self) -> dict[str, object]:
        return {
            "edge_id": self.edge_id,
            "context_count": self.context_count,
            "exact_context_count": self.exact_context_count,
            "ready": self.ready,
            "reason": self.reason,
            "action": dict(self.action) if self.action is not None else None,
        }


@dataclass(frozen=True)
class ProjectionReadinessReport:
    transitions: tuple[TransitionProjectionReadiness, ...]
    relevant_transition_count: int
    ready_transition_count: int
    rejected_context_count: int

    @property
    def ready(self) -> bool:
        return (
            self.relevant_transition_count > 0
            and self.ready_transition_count == self.relevant_transition_count
            and self.rejected_context_count == 0
        )

    def to_ir(self) -> dict[str, object]:
        return {
            "version": EVIDENCE_PROJECTION_VERSION,
            "ready": self.ready,
            "relevant_transition_count": self.relevant_transition_count,
            "ready_transition_count": self.ready_transition_count,
            "rejected_context_count": self.rejected_context_count,
            "transitions": [item.to_ir() for item in self.transitions],
        }


def audit_evidence_projection(
    machine_view: Mapping[str, object],
    *,
    evidence_field: str = "execution_evidence_v2",
    include_empty_evidence: bool = False,
) -> ProjectionReadinessReport:
    transitions: list[TransitionProjectionReadiness] = []
    rejected = 0
    relevant = 0
    ready = 0

    for index, transition in enumerate(_mappings(machine_view.get("transitions"))):
        evidence = _mapping(transition.get(evidence_field))
        if not evidence:
            continue
        contexts = _mappings(evidence.get("contexts"))
        if not contexts and not include_empty_evidence:
            continue
        relevant += 1
        decisions = tuple(check_exact_action_projection(context) for context in contexts)
        rejected += sum(not decision.allowed for decision in decisions)
        item = _transition_readiness(
            str(
                evidence.get("edge_id")
                or transition.get("id")
                or transition.get("edge_id")
                or index
            ),
            decisions,
        )
        transitions.append(item)
        ready += int(item.ready)

    return ProjectionReadinessReport(
        tuple(transitions),
        relevant,
        ready,
        rejected,
    )


def project_machine_from_evidence(
    machine_view: Mapping[str, object],
    *,
    mode: EvidenceProjectionMode = EvidenceProjectionMode.SHADOW,
    evidence_field: str = "execution_evidence_v2",
) -> dict[str, object]:
    """Publish or apply exact Evidence actions without AST or legacy strings.

    ``STRICT_EXACT`` with native ``rtai_execution_evidence_v2`` is fail closed:
    legacy System execution bindings are removed and ``system_action`` is supplied
    only by exact native Evidence. Machine-owned ``action`` data is not modified.
    """

    result = deepcopy(dict(machine_view))
    report = audit_evidence_projection(
        result,
        evidence_field=evidence_field,
        include_empty_evidence=True,
    )
    readiness = {item.edge_id: item for item in report.transitions}
    projected: list[dict[str, object]] = []
    native_evidence = evidence_field == "rtai_execution_evidence_v2"

    for index, original in enumerate(_mappings(result.get("transitions"))):
        transition = dict(original)
        evidence = _mapping(transition.get(evidence_field))
        edge_id = str(
            evidence.get("edge_id")
            or transition.get("id")
            or transition.get("edge_id")
            or index
        )
        item = readiness.get(edge_id)
        if item is not None:
            transition["evidence_projection"] = item.to_ir()
            if mode is not EvidenceProjectionMode.SHADOW:
                transition["evidence_projected_system_action"] = (
                    dict(item.action) if item.ready and item.action is not None else None
                )
                transition["evidence_projection_source"] = (
                    _projection_source_name(evidence_field)
                    if item.ready
                    else "unresolved-evidence"
                )
            if mode is EvidenceProjectionMode.STRICT_EXACT:
                strict_action = (
                    dict(item.action) if item.ready and item.action is not None else None
                )
                transition["evidence_display_action"] = strict_action
                transition["legacy_system_action_fallback_allowed"] = False
                transition["system_action"] = strict_action
                transition["system_action_projection_source"] = (
                    "rtai-execution-evidence-v2"
                    if native_evidence
                    else _projection_source_name(evidence_field)
                )
                if native_evidence:
                    transition["execution_action_bindings"] = []
                    transition["execution_contexts"] = []
                    transition["system_execution_actions"] = []
                    transition["system_actions"] = []
        projected.append(transition)

    analysis = dict(_mapping(result.get("analysis")))
    analysis.update(
        {
            "evidence_projection_version": EVIDENCE_PROJECTION_VERSION,
            "evidence_projection_mode": mode.value,
            "evidence_projection_field": evidence_field,
            "evidence_projection_ready": report.ready,
            "evidence_projection_relevant_transition_count": (
                report.relevant_transition_count
            ),
            "evidence_projection_ready_transition_count": report.ready_transition_count,
            "evidence_projection_rejected_context_count": report.rejected_context_count,
            "evidence_projection_legacy_fallback_allowed": (
                mode is not EvidenceProjectionMode.STRICT_EXACT
            ),
            "evidence_projection_native_source": native_evidence,
        }
    )
    result["transitions"] = projected
    result["evidence_projection_readiness"] = report.to_ir()
    result["analysis"] = analysis
    return result


def _transition_readiness(
    edge_id: str,
    decisions: Sequence[ExactActionDecision],
) -> TransitionProjectionReadiness:
    if not decisions:
        return TransitionProjectionReadiness(
            edge_id,
            0,
            0,
            False,
            "no-evidence-contexts",
            None,
        )
    allowed = tuple(decision for decision in decisions if decision.allowed)
    if len(allowed) != len(decisions):
        first = next(decision for decision in decisions if not decision.allowed)
        return TransitionProjectionReadiness(
            edge_id,
            len(decisions),
            len(allowed),
            False,
            first.reason,
            None,
        )

    actions = tuple(decision.action for decision in allowed)
    normalized = {_canonical_action(action) for action in actions}
    if len(normalized) != 1:
        return TransitionProjectionReadiness(
            edge_id,
            len(decisions),
            len(allowed),
            False,
            "exact-context-actions-disagree",
            None,
        )
    action = actions[0]
    return TransitionProjectionReadiness(
        edge_id,
        len(decisions),
        len(allowed),
        True,
        "all-contexts-have-equivalent-exact-evidence",
        action,
    )


def _projection_source_name(evidence_field: str) -> str:
    if evidence_field == "execution_evidence_v2":
        return "execution-evidence-v2"
    return evidence_field.replace("_", "-")


def _canonical_action(action: Mapping[str, object] | None) -> str:
    return json.dumps(
        dict(action) if action is not None else None,
        sort_keys=True,
        separators=(",", ":"),
        default=repr,
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mappings(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))

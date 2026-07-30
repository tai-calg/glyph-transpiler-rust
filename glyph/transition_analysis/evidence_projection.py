from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
import json
from typing import Mapping, Sequence

from .projection import ExactActionDecision, check_exact_action_projection


EVIDENCE_PROJECTION_VERSION = 1


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
) -> ProjectionReadinessReport:
    transitions: list[TransitionProjectionReadiness] = []
    rejected = 0
    relevant = 0
    ready = 0

    for index, transition in enumerate(_mappings(machine_view.get("transitions"))):
        evidence = _mapping(transition.get("execution_evidence_v2"))
        contexts = _mappings(evidence.get("contexts"))
        if not contexts:
            continue
        relevant += 1
        decisions = tuple(check_exact_action_projection(context) for context in contexts)
        rejected += sum(not decision.allowed for decision in decisions)
        item = _transition_readiness(
            str(evidence.get("edge_id") or transition.get("edge_id") or index),
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
) -> dict[str, object]:
    """Publish or apply exact Evidence actions without consulting AST/legacy strings.

    Shadow mode only attaches readiness metadata. ``PREFER_EXACT`` publishes an
    evidence projection candidate while retaining the active display field.
    ``STRICT_EXACT`` additionally makes ``evidence_display_action`` the explicit
    UI source and removes legacy fallback for relevant but unproven contexts. The
    main compiler pipeline does not enable strict mode yet.
    """

    result = deepcopy(dict(machine_view))
    report = audit_evidence_projection(result)
    readiness = {item.edge_id: item for item in report.transitions}
    projected: list[dict[str, object]] = []

    for index, original in enumerate(_mappings(result.get("transitions"))):
        transition = dict(original)
        evidence = _mapping(transition.get("execution_evidence_v2"))
        edge_id = str(evidence.get("edge_id") or transition.get("edge_id") or index)
        item = readiness.get(edge_id)
        if item is not None:
            transition["evidence_projection"] = item.to_ir()
            if mode is not EvidenceProjectionMode.SHADOW:
                transition["evidence_projected_system_action"] = (
                    dict(item.action) if item.ready and item.action is not None else None
                )
                transition["evidence_projection_source"] = (
                    "execution-evidence-v2" if item.ready else "unresolved-evidence"
                )
            if mode is EvidenceProjectionMode.STRICT_EXACT:
                transition["evidence_display_action"] = (
                    dict(item.action) if item.ready and item.action is not None else None
                )
                transition["legacy_system_action_fallback_allowed"] = False
        projected.append(transition)

    analysis = dict(_mapping(result.get("analysis")))
    analysis.update(
        {
            "evidence_projection_version": EVIDENCE_PROJECTION_VERSION,
            "evidence_projection_mode": mode.value,
            "evidence_projection_ready": report.ready,
            "evidence_projection_relevant_transition_count": (
                report.relevant_transition_count
            ),
            "evidence_projection_ready_transition_count": report.ready_transition_count,
            "evidence_projection_rejected_context_count": report.rejected_context_count,
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
    action = actions[0] if actions else None
    return TransitionProjectionReadiness(
        edge_id,
        len(decisions),
        len(allowed),
        True,
        "all-contexts-have-equivalent-exact-evidence",
        action,
    )


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

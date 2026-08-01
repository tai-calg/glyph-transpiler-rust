from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
import json
from typing import Mapping, Sequence

from .projection import ExactActionDecision, check_exact_action_projection
from .semantic_event import (
    attach_context_semantic_event_refs,
    attach_machine_action_aliases,
)


EVIDENCE_PROJECTION_VERSION = 6


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
    expected_transition_count: int
    relevant_transition_count: int
    ready_transition_count: int
    rejected_context_count: int
    missing_evidence_count: int

    @property
    def projection_complete(self) -> bool:
        return (
            len(self.transitions) == self.expected_transition_count
            and self.relevant_transition_count == self.expected_transition_count
        )

    @property
    def all_edges_exact(self) -> bool:
        return (
            self.projection_complete
            and self.expected_transition_count > 0
            and self.ready_transition_count == self.expected_transition_count
            and self.rejected_context_count == 0
            and self.missing_evidence_count == 0
        )

    @property
    def ready(self) -> bool:
        """Compatibility alias for the historical all-edges-Exact gate."""

        return self.all_edges_exact

    def to_ir(self) -> dict[str, object]:
        return {
            "version": EVIDENCE_PROJECTION_VERSION,
            "ready": self.ready,
            "projection_complete": self.projection_complete,
            "all_edges_exact": self.all_edges_exact,
            "expected_transition_count": self.expected_transition_count,
            "relevant_transition_count": self.relevant_transition_count,
            "ready_transition_count": self.ready_transition_count,
            "rejected_context_count": self.rejected_context_count,
            "missing_evidence_count": self.missing_evidence_count,
            "transitions": [item.to_ir() for item in self.transitions],
        }


def audit_evidence_projection(
    machine_view: Mapping[str, object],
    *,
    evidence_field: str = "execution_evidence_v2",
    include_empty_evidence: bool = False,
) -> ProjectionReadinessReport:
    """Audit every expected transition and reject ambiguous edge identity.

    ``include_empty_evidence`` means that a transition without the Evidence field is
    a rejected transition, not an invisible transition. This prevents a partial
    Evidence set from reporting ready by shrinking the denominator. Duplicate view
    edge IDs and Evidence whose edge ID differs from its owning transition are also
    rejected before any Exact Action is considered.
    """

    machine_transitions = _mappings(machine_view.get("transitions"))
    expected = len(machine_transitions)
    transition_edge_ids = tuple(
        _transition_edge_id(transition, index)
        for index, transition in enumerate(machine_transitions)
    )
    duplicate_edge_ids = {
        edge_id
        for edge_id, count in Counter(transition_edge_ids).items()
        if count > 1
    }
    transitions: list[TransitionProjectionReadiness] = []
    rejected = 0
    relevant = 0
    ready = 0
    missing = 0

    for index, transition in enumerate(machine_transitions):
        transition_edge_id = transition_edge_ids[index]
        evidence = _mapping(transition.get(evidence_field))
        evidence_edge_id = str(evidence.get("edge_id") or transition_edge_id)

        if transition_edge_id in duplicate_edge_ids:
            relevant += 1
            rejected += 1
            transitions.append(
                TransitionProjectionReadiness(
                    transition_edge_id,
                    0,
                    0,
                    False,
                    "duplicate-transition-edge-id",
                    None,
                )
            )
            continue

        if evidence and evidence_edge_id != transition_edge_id:
            relevant += 1
            rejected += 1
            transitions.append(
                TransitionProjectionReadiness(
                    transition_edge_id,
                    0,
                    0,
                    False,
                    "evidence-edge-id-mismatch",
                    None,
                )
            )
            continue

        if not evidence:
            if not include_empty_evidence:
                continue
            relevant += 1
            rejected += 1
            missing += 1
            transitions.append(
                TransitionProjectionReadiness(
                    transition_edge_id,
                    0,
                    0,
                    False,
                    "evidence-is-missing",
                    None,
                )
            )
            continue

        contexts = _mappings(evidence.get("contexts"))
        if not contexts and not include_empty_evidence:
            continue
        relevant += 1
        decisions = tuple(check_exact_action_projection(context) for context in contexts)
        rejected += sum(not decision.allowed for decision in decisions)
        item = _transition_readiness(
            transition_edge_id,
            decisions,
        )
        transitions.append(item)
        ready += int(item.ready)
        if not contexts:
            rejected += 1

    return ProjectionReadinessReport(
        tuple(transitions),
        expected,
        relevant,
        ready,
        rejected,
        missing,
    )


def project_machine_from_evidence(
    machine_view: Mapping[str, object],
    *,
    mode: EvidenceProjectionMode = EvidenceProjectionMode.SHADOW,
    evidence_field: str = "execution_evidence_v2",
) -> dict[str, object]:
    """Publish or apply exact Evidence actions without AST or legacy strings.

    ``STRICT_EXACT`` first removes every System-owned compatibility projection from
    every transition. It then restores a System Action only when native Evidence is
    exact and belongs unambiguously to that same transition. Missing, duplicate,
    mismatched or rejected Evidence therefore cannot leave a stale legacy Action.
    Native Effect events receive ordered semantic identities before projection;
    Machine display aliases are marked only when their complete invocation sequence
    matches those exact events. Machine-owned ``action`` data is not removed.
    """

    result = deepcopy(dict(machine_view))
    native_evidence = evidence_field == "rtai_execution_evidence_v2"
    if native_evidence:
        result = _attach_native_semantic_event_refs(result, evidence_field)

    report = audit_evidence_projection(
        result,
        evidence_field=evidence_field,
        include_empty_evidence=True,
    )
    readiness_by_transition = report.transitions
    projected: list[dict[str, object]] = []

    for index, original in enumerate(_mappings(result.get("transitions"))):
        transition = dict(original)
        evidence = _mapping(transition.get(evidence_field))
        edge_id = _transition_edge_id(transition, index)
        if mode is EvidenceProjectionMode.STRICT_EXACT:
            transition = _strict_sanitize_transition(
                transition,
                remove_legacy_evidence=native_evidence,
            )

        item = (
            readiness_by_transition[index]
            if index < len(readiness_by_transition)
            else None
        )
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
                if native_evidence and strict_action is not None:
                    transition = attach_machine_action_aliases(
                        transition,
                        strict_action,
                    )
                transition["evidence_display_action"] = strict_action
                transition["system_action"] = strict_action
                if strict_action is not None:
                    transition["system_action_projection_source"] = (
                        "rtai-execution-evidence-v2"
                        if native_evidence
                        else _projection_source_name(evidence_field)
                    )
                else:
                    transition.pop("system_action_projection_source", None)
        projected.append(transition)

    projection_safe = _projection_is_fail_closed(
        projected,
        mode=mode,
        native_evidence=native_evidence,
    )
    analysis = dict(_mapping(result.get("analysis")))
    analysis.update(
        {
            "evidence_projection_version": EVIDENCE_PROJECTION_VERSION,
            "evidence_projection_mode": mode.value,
            "evidence_projection_field": evidence_field,
            "evidence_projection_ready": report.ready,
            "evidence_projection_safe": projection_safe,
            "evidence_projection_complete": report.projection_complete,
            "evidence_projection_all_edges_exact": report.all_edges_exact,
            "evidence_projection_expected_transition_count": (
                report.expected_transition_count
            ),
            "evidence_projection_relevant_transition_count": (
                report.relevant_transition_count
            ),
            "evidence_projection_ready_transition_count": report.ready_transition_count,
            "evidence_projection_rejected_context_count": report.rejected_context_count,
            "evidence_projection_missing_evidence_count": report.missing_evidence_count,
            "evidence_projection_legacy_fallback_allowed": (
                mode is not EvidenceProjectionMode.STRICT_EXACT
            ),
            "evidence_projection_native_source": native_evidence,
            "evidence_projection_semantic_event_identity": native_evidence,
        }
    )
    result["transitions"] = projected
    readiness_ir = report.to_ir()
    readiness_ir["projection_safe"] = projection_safe
    result["evidence_projection_readiness"] = readiness_ir
    result["analysis"] = analysis
    return result


def _projection_is_fail_closed(
    transitions: Sequence[Mapping[str, object]],
    *,
    mode: EvidenceProjectionMode,
    native_evidence: bool,
) -> bool:
    if mode is not EvidenceProjectionMode.STRICT_EXACT:
        return False
    for transition in transitions:
        if transition.get("legacy_system_action_fallback_allowed") is not False:
            return False
        if transition.get("execution_action_bindings") != []:
            return False
        if transition.get("execution_contexts") != []:
            return False
        if transition.get("system_execution_actions") != []:
            return False
        if transition.get("system_actions") != []:
            return False
        action = transition.get("system_action")
        source = transition.get("system_action_projection_source")
        readiness = _mapping(transition.get("evidence_projection"))
        if action is None:
            if source is not None:
                return False
            continue
        if readiness.get("ready") is not True:
            return False
        expected_source = (
            "rtai-execution-evidence-v2"
            if native_evidence
            else _projection_source_name("execution_evidence_v2")
        )
        if native_evidence and source != expected_source:
            return False
    return True


def _attach_native_semantic_event_refs(
    machine_view: Mapping[str, object],
    evidence_field: str,
) -> dict[str, object]:
    result = deepcopy(dict(machine_view))
    transitions: list[dict[str, object]] = []
    for original in _mappings(result.get("transitions")):
        transition = dict(original)
        evidence = dict(_mapping(transition.get(evidence_field)))
        contexts: list[dict[str, object]] = []
        for raw_context in _mappings(evidence.get("contexts")):
            context = deepcopy(dict(raw_context))
            program_fingerprint = context.get("program_fingerprint")
            edge_fingerprint = context.get("analysis_edge_fingerprint")
            if isinstance(program_fingerprint, str) and program_fingerprint:
                attach_context_semantic_event_refs(
                    context,
                    program_fingerprint=program_fingerprint,
                    edge_fingerprint=(
                        edge_fingerprint
                        if isinstance(edge_fingerprint, str)
                        else None
                    ),
                )
            contexts.append(context)
        if evidence:
            evidence["contexts"] = contexts
            transition[evidence_field] = evidence
        transitions.append(transition)
    result["transitions"] = transitions
    return result


def _strict_sanitize_transition(
    transition: Mapping[str, object],
    *,
    remove_legacy_evidence: bool,
) -> dict[str, object]:
    result = dict(transition)
    result["legacy_system_action_fallback_allowed"] = False
    result["system_action"] = None
    result["execution_action_bindings"] = []
    result["execution_contexts"] = []
    result["system_execution_actions"] = []
    result["system_actions"] = []
    result["evidence_projected_system_action"] = None
    result["evidence_display_action"] = None
    result.pop("system_action_projection_source", None)
    if remove_legacy_evidence:
        result.pop("execution_evidence_v2", None)
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


def _transition_edge_id(
    transition: Mapping[str, object],
    index: int,
) -> str:
    return str(
        transition.get("id")
        or transition.get("edge_id")
        or index
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

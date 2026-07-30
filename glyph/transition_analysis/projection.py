from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ExactActionDecision:
    allowed: bool
    reason: str
    action: Mapping[str, object] | None = None

    def to_ir(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "action": dict(self.action) if self.action is not None else None,
        }


def check_exact_action_projection(
    context_evidence: Mapping[str, object],
) -> ExactActionDecision:
    """EvidenceだけからSystem Actionの確定表示可否を判定する。

    AST、CFG、solver、表示文字列へアクセスしない。Evidenceが満たす証明条件だけを
    検査し、条件が一つでも欠ける場合は確定表示を拒否する。
    """

    reachability = _mapping(context_evidence.get("reachability"))
    if reachability.get("status") != "proven-reachable":
        return ExactActionDecision(False, "reachability-is-not-proven")
    witness = reachability.get("witness")
    if not isinstance(witness, Mapping):
        return ExactActionDecision(False, "concrete-witness-is-missing")
    if witness.get("edge_id") != context_evidence.get("edge_id"):
        return ExactActionDecision(False, "concrete-witness-edge-mismatch")
    if not _is_exact(reachability, "reachability"):
        return ExactActionDecision(False, "reachability-is-not-exact")

    cardinality = _mapping(context_evidence.get("cardinality"))
    if cardinality.get("upper_bound") != "at-most-one":
        return ExactActionDecision(False, "transition-cardinality-is-not-at-most-one")
    if not _is_exact(cardinality, "cardinality"):
        return ExactActionDecision(False, "transition-cardinality-is-not-exact")

    effect_trace = _mapping(context_evidence.get("effect_trace"))
    if not _is_exact(effect_trace, "effect-trace"):
        return ExactActionDecision(False, "effect-trace-is-not-exact")
    if effect_trace.get("is_singleton") is not True:
        return ExactActionDecision(False, "effect-trace-is-not-singleton")

    completion = _mapping(context_evidence.get("completion"))
    if not _is_exact(completion, "completion"):
        return ExactActionDecision(False, "completion-is-not-exact")
    kinds = set(completion.get("kinds") or [])
    if not kinds or not kinds.issubset({"normal"}):
        return ExactActionDecision(False, "completion-is-not-uniformly-normal")

    if context_evidence.get("unknown_reasons"):
        return ExactActionDecision(False, "unknown-reasons-are-present")

    alternatives = effect_trace.get("alternatives")
    if not isinstance(alternatives, list) or len(alternatives) != 1:
        return ExactActionDecision(False, "effect-trace-structure-is-invalid")
    alternative = alternatives[0]
    if not isinstance(alternative, Mapping):
        return ExactActionDecision(False, "effect-trace-structure-is-invalid")
    events = alternative.get("events")
    if not isinstance(events, list):
        return ExactActionDecision(False, "effect-trace-events-are-invalid")
    if not events:
        return ExactActionDecision(True, "exact-no-system-action", None)
    if not all(isinstance(event, Mapping) for event in events):
        return ExactActionDecision(False, "effect-trace-events-are-invalid")
    action = {
        "kind": "effect-trace",
        "events": [dict(event) for event in events if isinstance(event, Mapping)],
    }
    return ExactActionDecision(True, "exact-action-evidence-satisfied", action)


def _is_exact(evidence: Mapping[str, object], required_scope: str) -> bool:
    approximation = _mapping(evidence.get("approximation"))
    proofs = approximation.get("proofs")
    if not isinstance(proofs, list):
        return False
    return (
        approximation.get("kind") == "exact"
        and not approximation.get("causes")
        and any(
            isinstance(proof, Mapping) and proof.get("scope") == required_scope
            for proof in proofs
        )
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}

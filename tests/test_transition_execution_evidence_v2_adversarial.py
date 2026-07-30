from __future__ import annotations

import unittest

from glyph.transition_analysis.exactness import (
    Approximation,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)
from glyph.transition_analysis.legacy_shadow import attach_execution_evidence_v2
from glyph.transition_analysis.projection import check_exact_action_projection


def exact(scope: ExactnessProofScope) -> dict[str, object]:
    return Approximation.exact(
        ExactnessProof(
            ExactnessProofKind.EXHAUSTIVE_FINITE_ORACLE,
            scope,
            "adversarial finite oracle",
        )
    ).to_ir()


def exact_context() -> dict[str, object]:
    edge_id = "Closed->Open@1"
    return {
        "edge_id": edge_id,
        "reachability": {
            "status": "proven-reachable",
            "witness": {"edge_id": edge_id},
            "approximation": exact(ExactnessProofScope.REACHABILITY),
        },
        "cardinality": {
            "upper_bound": "at-most-one",
            "approximation": exact(ExactnessProofScope.CARDINALITY),
        },
        "effect_trace": {
            "alternatives": [
                {
                    "condition": None,
                    "events": [
                        {
                            "operation": "actuator",
                            "expression": "actuator(Open)",
                        }
                    ],
                }
            ],
            "is_singleton": True,
            "approximation": exact(ExactnessProofScope.EFFECT_TRACE),
        },
        "completion": {
            "kinds": ["normal"],
            "approximation": exact(ExactnessProofScope.COMPLETION),
        },
        "unknown_reasons": [],
    }


class EvidenceV2AdversarialTests(unittest.TestCase):
    def test_proof_for_another_property_cannot_authorize_effect_trace(self) -> None:
        context = exact_context()
        context["effect_trace"]["approximation"] = exact(
            ExactnessProofScope.REACHABILITY
        )
        decision = check_exact_action_projection(context)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "effect-trace-is-not-exact")

    def test_edge_without_context_is_unknown_not_merely_over_approximate(self) -> None:
        evidenced = attach_execution_evidence_v2(
            {
                "transitions": [
                    {
                        "source_state": "Closed",
                        "target_state": "Open",
                        "execution_action_bindings": [],
                        "execution_contexts": [],
                    }
                ]
            }
        )
        evidence = evidenced["transitions"][0]["execution_evidence_v2"]
        self.assertEqual(evidence["approximation"]["kind"], "unknown")
        self.assertEqual(evidence["completion"]["kinds"], ["unknown"])

    def test_legacy_projection_cannot_override_exact_effect_trace(self) -> None:
        context = exact_context()
        context["legacy_projection"] = {"display": "fabricated()"}
        decision = check_exact_action_projection(context)
        self.assertTrue(decision.allowed)
        self.assertEqual(
            decision.action,
            {
                "kind": "effect-trace",
                "events": [
                    {
                        "operation": "actuator",
                        "expression": "actuator(Open)",
                    }
                ],
            },
        )


if __name__ == "__main__":
    unittest.main()

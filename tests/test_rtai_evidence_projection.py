from __future__ import annotations

import unittest

from glyph.transition_analysis.evidence_projection import (
    EvidenceProjectionMode,
    audit_evidence_projection,
    project_machine_from_evidence,
)


def exact(scope: str) -> dict[str, object]:
    return {
        "kind": "exact",
        "causes": [],
        "proofs": [
            {
                "kind": "structural-identity",
                "scope": scope,
                "detail": f"test {scope}",
            }
        ],
    }


def context(edge_id: str, operation: str = "actuator") -> dict[str, object]:
    return {
        "edge_id": edge_id,
        "system": "DoorControl",
        "entry": "control",
        "scope": "system",
        "reachability": {
            "status": "proven-reachable",
            "precondition": "True",
            "witness": {"edge_id": edge_id},
            "approximation": exact("reachability"),
        },
        "cardinality": {
            "upper_bound": "at-most-one",
            "witness": None,
            "approximation": exact("cardinality"),
        },
        "effect_trace": {
            "is_singleton": True,
            "alternatives": [
                {
                    "condition": None,
                    "events": [
                        {"operation": operation, "expression": f"{operation}(state)"}
                    ],
                }
            ],
            "approximation": exact("effect-trace"),
        },
        "completion": {
            "kinds": ["normal"],
            "approximation": exact("completion"),
        },
        "unknown_reasons": [],
    }


def machine(contexts: list[dict[str, object]]) -> dict[str, object]:
    return {
        "name": "Door",
        "analysis": {},
        "transitions": [
            {
                "edge_id": "Door:step:1:0",
                "display_action": {"kind": "legacy"},
                "execution_evidence_v2": {
                    "edge_id": "Door:step:1:0",
                    "contexts": contexts,
                },
            }
        ],
    }


class EvidenceProjectionTests(unittest.TestCase):
    def test_equivalent_exact_contexts_are_ready(self) -> None:
        value = machine(
            [
                context("Door:step:1:0"),
                context("Door:step:1:0"),
            ]
        )
        report = audit_evidence_projection(value)
        self.assertTrue(report.ready)
        self.assertEqual(report.ready_transition_count, 1)
        self.assertEqual(report.rejected_context_count, 0)

    def test_disagreeing_exact_contexts_are_not_ready(self) -> None:
        value = machine(
            [
                context("Door:step:1:0", "actuator"),
                context("Door:step:1:0", "alarm"),
            ]
        )
        report = audit_evidence_projection(value)
        self.assertFalse(report.ready)
        self.assertEqual(
            report.transitions[0].reason,
            "exact-context-actions-disagree",
        )

    def test_prefer_exact_publishes_candidate_without_replacing_display(self) -> None:
        value = machine([context("Door:step:1:0")])
        result = project_machine_from_evidence(
            value,
            mode=EvidenceProjectionMode.PREFER_EXACT,
        )
        transition = result["transitions"][0]
        self.assertEqual(transition["display_action"], {"kind": "legacy"})
        self.assertEqual(
            transition["evidence_projection_source"],
            "execution-evidence-v2",
        )
        self.assertEqual(
            transition["evidence_projected_system_action"]["kind"],
            "effect-trace",
        )

    def test_strict_mode_disables_legacy_fallback_for_unproven_context(self) -> None:
        invalid = context("Door:step:1:0")
        invalid["reachability"] = {
            **invalid["reachability"],
            "status": "may-reachable",
        }
        result = project_machine_from_evidence(
            machine([invalid]),
            mode=EvidenceProjectionMode.STRICT_EXACT,
        )
        transition = result["transitions"][0]
        self.assertIsNone(transition["evidence_display_action"])
        self.assertFalse(transition["legacy_system_action_fallback_allowed"])
        self.assertFalse(result["analysis"]["evidence_projection_ready"])


if __name__ == "__main__":
    unittest.main()

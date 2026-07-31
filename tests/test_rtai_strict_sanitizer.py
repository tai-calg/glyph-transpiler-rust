from __future__ import annotations

import unittest

from glyph.transition_analysis.evidence_projection import (
    EvidenceProjectionMode,
    audit_evidence_projection,
    project_machine_from_evidence,
)


def _machine_without_evidence() -> dict[str, object]:
    return {
        "name": "Door",
        "analysis": {},
        "transitions": [
            {
                "edge_id": "Door:step:1:0",
                "action": {"display": "machine_action()"},
                "machine_action": {"display": "machine_action()"},
                "system_action": {"display": "legacy_system_action()"},
                "system_action_projection_source": "legacy",
                "execution_action_bindings": [{"action": "legacy"}],
                "execution_contexts": [{"action": "legacy"}],
                "system_execution_actions": [{"action": "legacy"}],
                "system_actions": [{"action": "legacy"}],
            }
        ],
    }


class StrictSanitizerTests(unittest.TestCase):
    def test_missing_evidence_is_counted_as_rejected_transition(self) -> None:
        report = audit_evidence_projection(
            _machine_without_evidence(),
            evidence_field="rtai_execution_evidence_v2",
            include_empty_evidence=True,
        )

        self.assertFalse(report.ready)
        self.assertEqual(report.relevant_transition_count, 1)
        self.assertEqual(report.ready_transition_count, 0)
        self.assertEqual(report.rejected_context_count, 1)
        self.assertEqual(report.transitions[0].reason, "evidence-is-missing")

    def test_strict_mode_clears_stale_system_projection_before_audit(self) -> None:
        result = project_machine_from_evidence(
            _machine_without_evidence(),
            mode=EvidenceProjectionMode.STRICT_EXACT,
            evidence_field="rtai_execution_evidence_v2",
        )
        transition = result["transitions"][0]

        self.assertEqual(transition["action"], {"display": "machine_action()"})
        self.assertEqual(
            transition["machine_action"], {"display": "machine_action()"}
        )
        self.assertIsNone(transition["system_action"])
        self.assertIsNone(transition["evidence_display_action"])
        self.assertIsNone(transition["evidence_projected_system_action"])
        self.assertEqual(transition["execution_action_bindings"], [])
        self.assertEqual(transition["execution_contexts"], [])
        self.assertEqual(transition["system_execution_actions"], [])
        self.assertEqual(transition["system_actions"], [])
        self.assertFalse(transition["legacy_system_action_fallback_allowed"])
        self.assertNotIn("system_action_projection_source", transition)
        self.assertFalse(result["analysis"]["evidence_projection_ready"])

    def test_strict_sanitization_is_idempotent(self) -> None:
        first = project_machine_from_evidence(
            _machine_without_evidence(),
            mode=EvidenceProjectionMode.STRICT_EXACT,
            evidence_field="rtai_execution_evidence_v2",
        )
        second = project_machine_from_evidence(
            first,
            mode=EvidenceProjectionMode.STRICT_EXACT,
            evidence_field="rtai_execution_evidence_v2",
        )
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

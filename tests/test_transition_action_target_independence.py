from __future__ import annotations

import unittest

from glyph.transition_action_target_independence import (
    analyze_action_target_independence,
    semantic_name_key,
)


def transition(
    action: str,
    target: str,
    *,
    line: int = 1,
) -> dict[str, object]:
    return {
        "action": {
            "display": action,
            "expression": action,
            "variant": action.split("(", 1)[0],
        },
        "target_state": target,
        "source": {"line": line, "column": 1},
        "synthesized_failure": False,
    }


class TransitionActionTargetIndependenceTests(unittest.TestCase):
    def test_semantic_name_key_is_generic_over_inflection_and_role_suffixes(self) -> None:
        self.assertEqual(semantic_name_key("Stop"), semantic_name_key("Stopped"))
        self.assertEqual(
            semantic_name_key("RunAction"),
            semantic_name_key("RunningState"),
        )
        self.assertEqual(
            semantic_name_key("OpenValveCommand"),
            semantic_name_key("ValveOpenedMode"),
        )
        self.assertNotEqual(
            semantic_name_key("DisableMotor"),
            semantic_name_key("Stopped"),
        )

    def test_distinct_types_and_many_actions_to_one_state_prove_independence(self) -> None:
        analysis, diagnostics = analyze_action_target_independence(
            [
                transition("ApplyBrake", "Safe", line=10),
                transition("RemovePower", "Safe", line=11),
                transition("SetTorque(0.5)", "Driving", line=12),
            ],
            action_type="ActuatorCommand",
            state_type="OperatingMode",
        )
        self.assertTrue(analysis["typed_independent"])
        self.assertTrue(analysis["behaviorally_independent"])
        self.assertEqual(analysis["mapping_shape"], "many-actions-to-one-state")
        self.assertEqual(
            set(analysis["multiple_actions_to_state"]["Safe"]),
            {"ApplyBrake", "RemovePower"},
        )
        self.assertEqual(analysis["near_alias_count"], 0)
        self.assertEqual(diagnostics, [])

    def test_near_alias_is_reported_without_product_specific_names(self) -> None:
        analysis, diagnostics = analyze_action_target_independence(
            [transition("OpenValveAction", "ValveOpenedState", line=20)],
            action_type="ValveCommand",
            state_type="ValveMode",
        )
        self.assertEqual(analysis["near_alias_count"], 1)
        self.assertIn(
            "STIR_ACTION_TARGET_NEAR_ALIAS",
            {item["code"] for item in diagnostics},
        )

    def test_one_to_one_mapping_is_reported_as_redundant_axis(self) -> None:
        analysis, diagnostics = analyze_action_target_independence(
            [
                transition("EnableCurrent", "Active", line=30),
                transition("RemoveCurrent", "Inactive", line=31),
            ],
            action_type="PowerCommand",
            state_type="PowerMode",
        )
        self.assertFalse(analysis["behaviorally_independent"])
        self.assertEqual(analysis["mapping_shape"], "one-to-one")
        self.assertIn(
            "STIR_ACTION_TARGET_REDUNDANT_AXIS",
            {item["code"] for item in diagnostics},
        )

    def test_same_projection_type_is_reported(self) -> None:
        analysis, diagnostics = analyze_action_target_independence(
            [transition("Active", "Inactive", line=40)],
            action_type="Mode",
            state_type="Mode",
        )
        self.assertFalse(analysis["typed_independent"])
        self.assertIn(
            "STIR_ACTION_TARGET_TYPE_ALIAS",
            {item["code"] for item in diagnostics},
        )

    def test_synthesized_failure_does_not_fabricate_independence(self) -> None:
        item = transition("Reset", "Faulted")
        item["synthesized_failure"] = True
        analysis, diagnostics = analyze_action_target_independence(
            [transition("Start", "Running"), item],
            action_type="Command",
            state_type="Mode",
        )
        self.assertEqual(analysis["pair_count"], 1)
        self.assertFalse(analysis["behaviorally_independent"])
        self.assertNotIn(
            "STIR_ACTION_TARGET_REDUNDANT_AXIS",
            {entry["code"] for entry in diagnostics},
        )


if __name__ == "__main__":
    unittest.main()

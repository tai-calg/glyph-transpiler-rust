from __future__ import annotations

import unittest
from pathlib import Path

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views


ROOT = Path(__file__).resolve().parents[1]


def compile_example(relative: str) -> dict[str, object]:
    path = ROOT / relative
    output = CompilationPipeline().compile_text(
        path.read_text(encoding="utf-8"),
        source_name=str(path),
    )
    return build_io_state_views(output.model, output.diagrams.ir)


def action_display(transition: dict[str, object]) -> str:
    action = transition.get("action")
    if not isinstance(action, dict):
        return ""
    return str(action.get("display") or action.get("expression") or "")


class TransitionInputProvenanceTests(unittest.TestCase):
    def test_motor_decision_preimage_becomes_input_and_command_becomes_action(self) -> None:
        views = compile_example("examples/acceptance/motor_safety.glyph")
        machine = views["state"]["machines"][0]

        self.assertEqual(views["transition_semantics_version"], 2)
        self.assertEqual(views["transition_input_preimage_version"], 1)
        self.assertGreater(machine["analysis"]["expanded_input_preimage_count"], 0)
        self.assertEqual(machine["analysis"]["unresolved_input_preimage_count"], 0)

        stopped = [
            item
            for item in machine["transitions"]
            if item["target_state"] == "Stopped"
            and action_display(item) == "Stop"
            and item.get("input_preimage")
        ]
        self.assertTrue(stopped)
        for item in stopped:
            trigger = item["trigger"]
            display = trigger["display"]
            self.assertEqual(trigger["confidence"], "dataflow-expanded")
            self.assertEqual(trigger["provenance"], "decision-output-preimage")
            self.assertEqual(trigger["decision_function"], "decide")
            self.assertIn("input.emergency", display)
            self.assertIn("input.fault", display)
            self.assertIn("input.enabled", display)
            self.assertNotEqual(display, "Stop")
            self.assertNotEqual(display, action_display(item))
            self.assertNotEqual(action_display(item), item["target_state"])

        running = [
            item
            for item in machine["transitions"]
            if item["target_state"] == "Running"
            and item.get("input_preimage")
        ]
        self.assertTrue(running)
        for item in running:
            self.assertEqual(item["trigger"]["display"], "otherwise")
            self.assertEqual(item["trigger"]["confidence"], "dataflow-expanded")
            self.assertEqual(
                action_display(item),
                "Drive(normalize(input.raw))",
            )
            self.assertNotEqual(item["trigger"]["display"], action_display(item))
            self.assertNotEqual(action_display(item), item["target_state"])

    def test_door_decision_preimage_keeps_input_action_and_target_independent(self) -> None:
        views = compile_example("examples/acceptance/door_controller.glyph")
        machine = views["state"]["machines"][0]
        expanded = [item for item in machine["transitions"] if item.get("input_preimage")]
        self.assertTrue(expanded)

        alarm = next(
            item
            for item in expanded
            if item["target_state"] == "Alarmed"
            and action_display(item) == "RaiseAlarm"
        )
        self.assertIn("input.forced_open", alarm["trigger"]["display"])
        self.assertNotEqual(alarm["trigger"]["display"], "RaiseAlarm")

        unlock = next(
            item
            for item in expanded
            if item["target_state"] == "Unlocked"
            and action_display(item) == "Unlock"
        )
        self.assertIn("authenticate(input)", unlock["trigger"]["display"])
        self.assertIn("input.request_open", unlock["trigger"]["display"])
        self.assertNotEqual(unlock["trigger"]["display"], "Unlock")

        locked = next(
            item
            for item in expanded
            if item["target_state"] == "Locked"
            and action_display(item) == "KeepLocked"
        )
        self.assertEqual(locked["trigger"]["display"], "otherwise")

        for item in (alarm, unlock, locked):
            self.assertNotEqual(item["trigger"]["display"], action_display(item))
            self.assertNotEqual(action_display(item), item["target_state"])
            self.assertEqual(item.get("effect_invocations"), [])


if __name__ == "__main__":
    unittest.main()

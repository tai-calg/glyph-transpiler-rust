from __future__ import annotations

import unittest
from pathlib import Path
from typing import Mapping

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


def output_variant(transition: Mapping[str, object]) -> str:
    value = transition.get("emitted_output")
    return str(value.get("variant") or "") if isinstance(value, Mapping) else ""


def action_display(transition: Mapping[str, object]) -> str:
    value = transition.get("action")
    return str(value.get("display") or "") if isinstance(value, Mapping) else ""


class TransitionOperationActionTests(unittest.TestCase):
    def test_motor_action_is_executed_operation_not_state_output(self) -> None:
        views = compile_example("examples/acceptance/motor_safety.glyph")
        self.assertEqual(views["transition_operation_action_version"], 2)
        machine = views["state"]["machines"][0]
        self.assertEqual(machine["analysis"]["state_field_action_count"], 0)

        expected = {
            "LatchFault": ("write_motor(LatchFault)", "Faulted"),
            "EmergencyBrake": ("write_motor(EmergencyBrake)", "Stopped"),
            "DisableMotor": ("write_motor(DisableMotor)", "Stopped"),
            "SetMotorPower": (
                "write_motor(SetMotorPower(normalize(input.raw)))",
                "Running",
            ),
        }
        for variant, (action, target) in expected.items():
            transition = next(
                item
                for item in machine["transitions"]
                if output_variant(item) == variant and item.get("input_preimage")
            )
            self.assertEqual(action_display(transition), action)
            self.assertEqual(transition["target_state"], target)
            self.assertEqual(
                transition["action"]["provenance"],
                "transition-operation-invocation",
            )
            self.assertNotEqual(action_display(transition), variant)
            self.assertNotEqual(action_display(transition), target)
            self.assertEqual(len(transition["action_invocations"]), 1)
            self.assertEqual(
                transition["action_invocations"][0]["expression"],
                action,
            )

    def test_state_carried_door_command_is_not_rendered_as_action(self) -> None:
        views = compile_example("examples/acceptance/door_controller.glyph")
        machine = views["state"]["machines"][0]
        transitions = [
            item
            for item in machine["transitions"]
            if output_variant(item) in {"RaiseAlarm", "Unlock", "KeepLocked"}
        ]
        self.assertTrue(transitions)
        for transition in transitions:
            self.assertIsNone(transition["action"])
            self.assertEqual(transition["action_invocations"], [])
            self.assertIsNotNone(transition["emitted_output"])

    def test_target_state_is_never_action_fallback(self) -> None:
        views = compile_example("examples/state_diagrams/session_protocol.glyph")
        machine = views["state"]["machines"][0]
        for transition in machine["transitions"]:
            action = action_display(transition)
            if action:
                self.assertNotEqual(action, transition["target_state"])
            else:
                self.assertIsNone(transition["action"])


if __name__ == "__main__":
    unittest.main()

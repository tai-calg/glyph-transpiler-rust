from __future__ import annotations

import unittest
from pathlib import Path

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "state_diagrams"


def compile_example(name: str) -> dict[str, object]:
    path = EXAMPLES / name
    source = path.read_text(encoding="utf-8")
    output = CompilationPipeline().compile_text(source, source_name=str(path))
    return build_io_state_views(output.model, output.diagrams.ir)


def transition_pairs(machine: dict[str, object]) -> set[tuple[str, str]]:
    return {
        (str(item["source_state"]), str(item["target_state"]))
        for item in machine["transitions"]
    }


def diagnostic_codes(machine: dict[str, object]) -> set[str]:
    return {str(item["code"]) for item in machine["diagnostics"]}


class GenericStateDiagramExamplesTests(unittest.TestCase):
    def test_traffic_light_cycle_and_global_fault_are_normalized(self) -> None:
        views = compile_example("traffic_light.glyph")
        machine = views["state"]["machines"][0]

        self.assertEqual(machine["name"], "Traffic")
        self.assertEqual(machine["initial_state"], "Red")
        self.assertEqual(
            {state["name"] for state in machine["states"]},
            {"Red", "Green", "Yellow", "TrafficFault"},
        )
        self.assertEqual(machine["unreachable_states"], [])
        self.assertEqual(machine["analysis"]["reachable_state_count"], 4)
        self.assertEqual(machine["analysis"]["state_count"], 4)
        self.assertEqual(machine["analysis"]["normalized_transition_count"], 11)
        self.assertFalse(
            any(
                item["source_state"] == "*" or item["target_state"] == "*"
                for item in machine["transitions"]
            )
        )

        pairs = transition_pairs(machine)
        self.assertTrue(
            {
                ("Red", "Green"),
                ("Green", "Yellow"),
                ("Yellow", "Red"),
                ("Red", "TrafficFault"),
                ("Green", "TrafficFault"),
                ("Yellow", "TrafficFault"),
                ("TrafficFault", "TrafficFault"),
            }.issubset(pairs)
        )
        self.assertNotIn("unreachable-state", diagnostic_codes(machine))
        self.assertNotIn("state-independent-transition", diagnostic_codes(machine))

    def test_nested_session_transition_function_is_followed(self) -> None:
        views = compile_example("session_protocol.glyph")
        machine = views["state"]["machines"][0]

        self.assertEqual(machine["name"], "Session")
        self.assertEqual(machine["initial_state"], "SessionIdle")
        self.assertEqual(machine["unreachable_states"], [])
        self.assertEqual(machine["analysis"]["reachable_state_count"], 4)
        self.assertEqual(
            machine["analysis"]["function_closure"][:2],
            ["session_step", "session_transition"],
        )

        pairs = transition_pairs(machine)
        self.assertTrue(
            {
                ("SessionIdle", "SessionConnecting"),
                ("SessionConnecting", "SessionReady"),
                ("SessionConnecting", "SessionFailed"),
                ("SessionReady", "SessionIdle"),
                ("SessionFailed", "SessionIdle"),
            }.issubset(pairs)
        )
        self.assertFalse(
            any(
                item["source_state"] == "*" or item["target_state"] == "*"
                for item in machine["transitions"]
            )
        )
        self.assertEqual(machine["diagnostics"], [])

    def test_multiple_machines_are_analyzed_independently(self) -> None:
        views = compile_example("dual_machines.glyph")
        machines = {machine["name"]: machine for machine in views["state"]["machines"]}

        self.assertEqual(set(machines), {"Door", "Power"})

        door = machines["Door"]
        self.assertEqual(door["initial_state"], "DoorClosed")
        self.assertEqual(door["unreachable_states"], ["DoorJammed"])
        self.assertIn("unreachable-state", diagnostic_codes(door))
        self.assertTrue(
            {
                ("DoorClosed", "DoorOpen"),
                ("DoorOpen", "DoorClosed"),
            }.issubset(transition_pairs(door))
        )

        power = machines["Power"]
        self.assertEqual(power["initial_state"], "PowerOff")
        self.assertEqual(power["unreachable_states"], [])
        self.assertEqual(power["analysis"]["reachable_state_count"], 3)
        self.assertTrue(
            {
                ("PowerOff", "PowerOn"),
                ("PowerOn", "PowerOff"),
                ("PowerOff", "PowerFault"),
                ("PowerOn", "PowerFault"),
                ("PowerFault", "PowerFault"),
            }.issubset(transition_pairs(power))
        )
        self.assertNotIn("unreachable-state", diagnostic_codes(power))


if __name__ == "__main__":
    unittest.main()

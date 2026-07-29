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


def compile_source(source: str, name: str = "input-preimage-inline.glyph") -> dict[str, object]:
    output = CompilationPipeline().compile_text(source, source_name=name)
    return build_io_state_views(output.model, output.diagrams.ir)


def action_display(transition: dict[str, object]) -> str:
    action = transition.get("action")
    if not isinstance(action, dict):
        return ""
    return str(action.get("display") or action.get("expression") or "")


def output_display(transition: dict[str, object]) -> str:
    emitted = transition.get("emitted_output")
    if not isinstance(emitted, dict):
        return ""
    return str(emitted.get("display") or emitted.get("expression") or "")


def output_variant(transition: dict[str, object]) -> str:
    emitted = transition.get("emitted_output")
    if not isinstance(emitted, dict):
        return ""
    return str(emitted.get("variant") or "")


def first_case(transition: dict[str, object]) -> dict[str, object]:
    cases = transition.get("enabling_cases", [])
    if not cases:
        raise AssertionError(f"transition lacks enabling_cases: {transition}")
    return cases[0]


def expanded_signature(views: dict[str, object], output: str) -> tuple[str, str, str]:
    machine = views["state"]["machines"][0]
    item = next(
        transition
        for transition in machine["transitions"]
        if output_display(transition) == output and transition.get("input_preimage")
    )
    case = first_case(item)
    input_pattern = case.get("input_pattern") or {}
    return str(input_pattern.get("display") or ""), output_display(item), item["target_state"]


_METAMORPHIC_SOURCE = """\
machine Example(state:ExampleState,input:Input)
  select=state.mode
  action=state.action
  init=ExampleState(Idle,Stay)
  next=step(state,input)
  success=Active
  failure=Faulted

*Input(start,enabled:B)
+Action=Stay|Go
+Mode=Idle|Active|Faulted
*ExampleState(mode:Mode,action:Action)

>decide(input:Input):Action
  input.start >> Go
  _ >> Stay

>step(state:ExampleState,input:Input):ExampleState
  action := decide(input)
  next :=
    action==Go >> ExampleState(Active,Go)
    action==Stay >> ExampleState(Idle,Stay)
    _ >> ExampleState(Faulted,Stay)
  next
"""


class TransitionInputProvenanceTests(unittest.TestCase):
    def test_motor_decision_preimage_becomes_input_and_command_remains_output(self) -> None:
        views = compile_example("examples/acceptance/motor_safety.glyph")
        machine = views["state"]["machines"][0]

        self.assertEqual(views["transition_semantics_version"], 2)
        self.assertEqual(views["transition_input_preimage_version"], 1)
        self.assertEqual(views["transition_enabling_cases_version"], 1)
        self.assertEqual(views["transition_operation_action_version"], 2)
        self.assertEqual(views["transition_action_target_independence_version"], 1)
        self.assertGreater(machine["analysis"]["expanded_input_preimage_count"], 0)
        self.assertEqual(machine["analysis"]["unresolved_input_preimage_count"], 0)

        emergency = next(
            item
            for item in machine["transitions"]
            if item["target_state"] == "Stopped"
            and output_variant(item) == "EmergencyBrake"
            and item.get("input_preimage")
        )
        emergency_case = first_case(emergency)
        self.assertEqual(
            emergency_case["input_pattern"]["display"],
            "input.emergency",
        )
        self.assertEqual(emergency_case["guard"]["display"], "!input.fault")
        self.assertEqual(
            emergency["trigger"]["provenance"],
            "decision-output-preimage",
        )
        self.assertEqual(action_display(emergency), "write_motor(EmergencyBrake)")
        self.assertEqual(output_display(emergency), "EmergencyBrake")

        disabled = next(
            item
            for item in machine["transitions"]
            if item["target_state"] == "Stopped"
            and output_variant(item) == "DisableMotor"
            and item.get("input_preimage")
        )
        disabled_case = first_case(disabled)
        self.assertEqual(disabled_case["input_pattern"]["display"], "!input.enabled")
        self.assertEqual(action_display(disabled), "write_motor(DisableMotor)")

        faulted = next(
            item
            for item in machine["transitions"]
            if item["target_state"] == "Faulted"
            and output_variant(item) == "LatchFault"
            and item.get("input_preimage")
        )
        self.assertEqual(first_case(faulted)["input_pattern"]["display"], "input.fault")
        self.assertEqual(action_display(faulted), "write_motor(LatchFault)")

        running = [
            item
            for item in machine["transitions"]
            if item["target_state"] == "Running"
            and item.get("input_preimage")
        ]
        self.assertTrue(running)
        for item in running:
            case = first_case(item)
            self.assertIsNone(case["input_pattern"])
            self.assertEqual(case["guard"]["display"], "otherwise")
            self.assertIsNone(item["trigger"])
            self.assertEqual(
                action_display(item),
                "write_motor(SetMotorPower(normalize(input.raw)))",
            )
            self.assertEqual(
                output_display(item),
                "SetMotorPower(normalize(input.raw))",
            )
            self.assertNotEqual(action_display(item), item["target_state"])
            self.assertNotEqual(action_display(item), output_display(item))

        independence = machine["analysis"]["action_target_independence"]
        self.assertTrue(independence["typed_independent"])
        self.assertEqual(independence["action_type"], "OperationInvocation")
        self.assertEqual(independence["state_type"], "Mode")
        self.assertTrue(independence["behaviorally_independent"])
        self.assertGreater(independence["behavioral_witness_count"], 0)
        self.assertEqual(independence["near_alias_count"], 0)
        self.assertEqual(
            set(independence["action_to_multiple_states"]["write_motor"]),
            {"Faulted", "Running", "Stopped"},
        )

    def test_door_decision_preimage_keeps_output_separate_from_action(self) -> None:
        views = compile_example("examples/acceptance/door_controller.glyph")
        machine = views["state"]["machines"][0]
        expanded = [item for item in machine["transitions"] if item.get("input_preimage")]
        self.assertTrue(expanded)

        alarm = next(
            item
            for item in expanded
            if item["target_state"] == "Alarmed"
            and output_variant(item) == "RaiseAlarm"
        )
        alarm_case = first_case(alarm)
        self.assertIn("input.forced_open", alarm_case["input_pattern"]["display"])
        self.assertEqual(output_display(alarm), "RaiseAlarm")

        unlock = next(
            item
            for item in expanded
            if item["target_state"] == "Unlocked"
            and output_variant(item) == "Unlock"
        )
        unlock_case = first_case(unlock)
        self.assertEqual(unlock_case["input_pattern"]["display"], "input.request_open")
        self.assertIn("authenticate(input)", unlock_case["guard"]["display"])
        self.assertNotIn("authenticate(input)", unlock_case["input_pattern"]["display"])

        locked = next(
            item
            for item in expanded
            if item["target_state"] == "Locked"
            and output_variant(item) == "KeepLocked"
        )
        locked_case = first_case(locked)
        self.assertIsNone(locked_case["input_pattern"])
        self.assertEqual(locked_case["guard"]["display"], "otherwise")

        expected_operations = {
            "RaiseAlarm": "alarm",
            "Unlock": "lock",
            "KeepLocked": "lock",
        }
        for item in (alarm, unlock, locked):
            operation = expected_operations[output_variant(item)]
            self.assertTrue(
                action_display(item).startswith(f"{operation}(DoorState("),
                action_display(item),
            )
            self.assertEqual(len(item.get("action_invocations", [])), 1)
            self.assertEqual(
                item["action_invocations"][0]["provenance"],
                "transition-result-consumer",
            )
            self.assertEqual(
                [effect["expression"] for effect in item.get("effect_invocations", [])],
                [action_display(item)],
            )
            self.assertNotEqual(action_display(item), output_display(item))
            self.assertNotEqual(action_display(item), item["target_state"])
            self.assertNotEqual(output_display(item), item["target_state"])

    def test_target_rename_changes_only_target_axis(self) -> None:
        baseline = expanded_signature(compile_source(_METAMORPHIC_SOURCE), "Go")
        renamed_source = _METAMORPHIC_SOURCE.replace("Active", "Working")
        renamed = expanded_signature(compile_source(renamed_source), "Go")
        self.assertEqual(renamed[0], baseline[0])
        self.assertEqual(renamed[1], baseline[1])
        self.assertEqual(baseline[2], "Active")
        self.assertEqual(renamed[2], "Working")

    def test_emitted_output_rename_changes_only_output_axis(self) -> None:
        baseline = expanded_signature(compile_source(_METAMORPHIC_SOURCE), "Go")
        renamed_source = _METAMORPHIC_SOURCE.replace("Go", "Begin")
        renamed = expanded_signature(compile_source(renamed_source), "Begin")
        self.assertEqual(renamed[0], baseline[0])
        self.assertEqual(renamed[2], baseline[2])
        self.assertEqual(baseline[1], "Go")
        self.assertEqual(renamed[1], "Begin")

    def test_predicate_change_changes_only_input_axis(self) -> None:
        baseline = expanded_signature(compile_source(_METAMORPHIC_SOURCE), "Go")
        changed_source = _METAMORPHIC_SOURCE.replace(
            "input.start >> Go",
            "input.start&input.enabled >> Go",
        )
        changed = expanded_signature(compile_source(changed_source), "Go")
        self.assertNotEqual(changed[0], baseline[0])
        self.assertIn("input.enabled", changed[0])
        self.assertEqual(changed[1], baseline[1])
        self.assertEqual(changed[2], baseline[2])


if __name__ == "__main__":
    unittest.main()

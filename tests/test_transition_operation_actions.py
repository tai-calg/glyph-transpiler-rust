from __future__ import annotations

import unittest
from pathlib import Path
from typing import Mapping

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views


ROOT = Path(__file__).resolve().parents[1]


def compile_source(source: str) -> dict[str, object]:
    output = CompilationPipeline().compile_text(source, source_name="test.glyph")
    return build_io_state_views(output.model, output.diagrams.ir)


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


def _display(value: object) -> str:
    return str(value.get("display") or "") if isinstance(value, Mapping) else ""


def action_display(transition: Mapping[str, object]) -> str:
    return _display(transition.get("display_action") or transition.get("action"))


def machine_action_display(transition: Mapping[str, object]) -> str:
    return _display(transition.get("machine_action"))


def execution_bindings(transition: Mapping[str, object]) -> list[Mapping[str, object]]:
    return [
        item
        for item in transition.get("execution_action_bindings", [])
        if isinstance(item, Mapping)
    ]


DIRECT_ACTUATOR_SOURCE = """system DoorControl
  entry control

  in state:DoorState
  in input:Input
  out receipt:Receipt

  state -> control
  input -> control
  control -> receipt
  control -> actuator

machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*Input(open_request,authorized,obstruction:B)
+DoorMode=Closed|Opening|Open|Alarm
*DoorState(mode:DoorMode)
*Receipt(state:DoorState)

!actuator(state:DoorState):Receipt

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request&input.authorized >> DoorState(Opening)
  state.mode==Opening&input.obstruction >> DoorState(Alarm)
  state.mode==Opening >> DoorState(Open)
  _ >> state

>control(state:DoorState,input:Input):Receipt
  next := step(state,input)
  actuator(next)
"""


STRUCTURAL_STATE_SOURCE = """system DeviceControl
  entry control

  in state:DeviceState
  in input:Input
  out receipt:Receipt

  state -> control
  input -> control
  control -> receipt
  control -> actuator

machine Device(state:DeviceState,input:Input)
  select=state.mode
  init=DeviceState(Idle,0)
  next=step(state,input)
  success=Active
  failure=Faulted

*Input(start:B)
+Mode=Idle|Active|Faulted
*DeviceState(mode:Mode,count:U)
*Receipt(state:DeviceState)

!actuator(state:DeviceState):Receipt

>step(state:DeviceState,input:Input):DeviceState
  state.mode==Idle&input.start >> DeviceState(Active,state.count+1)
  state.mode==Active >> DeviceState(Idle,state.count)
  _ >> state

>control(state:DeviceState,input:Input):Receipt
  next := step(state,input)
  actuator(next)
"""


class TransitionOperationActionTests(unittest.TestCase):
    def test_machine_operation_is_not_state_output_or_system_action(self) -> None:
        views = compile_example("examples/acceptance/motor_safety.glyph")
        self.assertEqual(views["transition_operation_action_version"], 2)
        self.assertEqual(views["transition_action_scope_version"], 1)
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
            self.assertEqual(machine_action_display(transition), action)
            self.assertEqual(action_display(transition), action)
            self.assertEqual(transition["target_state"], target)
            self.assertEqual(
                transition["machine_action"]["provenance"],
                "transition-operation-invocation",
            )
            self.assertEqual(
                transition["display_action"]["provenance"],
                "transition-display-action-projection",
            )
            self.assertEqual(transition["action_scope"]["display_scope"], "machine")
            self.assertEqual(execution_bindings(transition), [])
            self.assertNotEqual(action_display(transition), variant)
            self.assertNotEqual(action_display(transition), target)

    def test_system_result_consumer_is_not_machine_action(self) -> None:
        views = compile_example("examples/acceptance/door_controller.glyph")
        self.assertEqual(views["transition_result_consumer_action_version"], 2)
        machine = views["state"]["machines"][0]
        expected_operations = {
            "RaiseAlarm": "alarm",
            "Unlock": "lock",
            "KeepLocked": "lock",
        }
        transitions = [
            item
            for item in machine["transitions"]
            if output_variant(item) in expected_operations and item.get("input_preimage")
        ]
        self.assertTrue(transitions)
        for transition in transitions:
            variant = output_variant(transition)
            operation = expected_operations[variant]
            action = action_display(transition)
            self.assertEqual(machine_action_display(transition), "")
            self.assertTrue(action.startswith(f"{operation}(DoorState("), action)
            bindings = execution_bindings(transition)
            self.assertEqual(len(bindings), 1)
            self.assertEqual(bindings[0]["system"], "DoorControl")
            self.assertEqual(bindings[0]["entry"], "control")
            self.assertEqual(
                bindings[0]["action_invocations"][0]["provenance"],
                "transition-result-consumer",
            )
            self.assertEqual(transition["action_scope"]["display_scope"], "system")
            self.assertNotEqual(action, variant)
            self.assertNotEqual(action, transition["target_state"])

    def test_direct_caller_binding_is_specialized_per_transition(self) -> None:
        views = compile_source(DIRECT_ACTUATOR_SOURCE)
        machine = views["state"]["machines"][0]
        opening = next(
            item for item in machine["transitions"] if item["target_state"] == "Opening"
        )
        alarm = next(
            item for item in machine["transitions"] if item["target_state"] == "Alarm"
        )
        self.assertEqual(action_display(opening), "actuator(DoorState(Opening))")
        self.assertEqual(action_display(alarm), "actuator(DoorState(Alarm))")
        self.assertIsNone(opening["machine_action"])

    def test_direct_nested_transition_call_is_detected(self) -> None:
        source = DIRECT_ACTUATOR_SOURCE.replace(
            "  next := step(state,input)\n  actuator(next)\n",
            "  actuator(step(state,input))\n",
        )
        views = compile_source(source)
        machine = views["state"]["machines"][0]
        opening = next(
            item for item in machine["transitions"] if item["target_state"] == "Opening"
        )
        self.assertEqual(action_display(opening), "actuator(DoorState(Opening))")
        self.assertEqual(execution_bindings(opening)[0]["entry"], "control")

    def test_pure_wrapper_around_transition_call_is_detected(self) -> None:
        source = DIRECT_ACTUATOR_SOURCE.replace(
            ">control(state:DoorState,input:Input):Receipt\n",
            ">identity(value:DoorState):DoorState=value\n\n>control(state:DoorState,input:Input):Receipt\n",
        ).replace(
            "  next := step(state,input)\n",
            "  next := identity(step(state,input))\n",
        )
        views = compile_source(source)
        machine = views["state"]["machines"][0]
        opening = next(
            item for item in machine["transitions"] if item["target_state"] == "Opening"
        )
        self.assertEqual(action_display(opening), "actuator(DoorState(Opening))")

    def test_same_state_result_is_structurally_specialized(self) -> None:
        views = compile_source(STRUCTURAL_STATE_SOURCE)
        machine = views["state"]["machines"][0]
        transitions = [
            item
            for item in machine["transitions"]
            if not item.get("synthesized_failure")
        ]
        signature = {
            (item["source_state"], item["target_state"]): action_display(item)
            for item in transitions
        }
        self.assertEqual(
            signature[("Idle", "Idle")],
            "actuator(DeviceState(Idle,state.count))",
        )
        self.assertEqual(
            signature[("Faulted", "Faulted")],
            "actuator(DeviceState(Faulted,state.count))",
        )
        self.assertEqual(
            signature[("Idle", "Active")],
            "actuator(DeviceState(Active,state.count+1))",
        )
        self.assertEqual(
            signature[("Active", "Idle")],
            "actuator(DeviceState(Idle,state.count))",
        )
        self.assertNotIn(("Active", "Active"), signature)
        self.assertFalse(any("actuator(state)" in value for value in signature.values()))

    def test_alias_chain_preserves_transition_result_provenance(self) -> None:
        source = DIRECT_ACTUATOR_SOURCE.replace(
            "  actuator(next)\n",
            "  forwarded := next\n  actuator(forwarded)\n",
        )
        views = compile_source(source)
        machine = views["state"]["machines"][0]
        opening = next(
            item for item in machine["transitions"] if item["target_state"] == "Opening"
        )
        self.assertEqual(action_display(opening), "actuator(DoorState(Opening))")

    def test_unrelated_post_step_effect_is_not_invented_as_action(self) -> None:
        source = (
            DIRECT_ACTUATOR_SOURCE.replace(
                "  control -> actuator\n",
                "  control -> tick\n",
            )
            .replace(
                "!actuator(state:DoorState):Receipt\n",
                "!actuator(state:DoorState):Receipt\n!tick():Receipt\n",
            )
            .replace("  actuator(next)\n", "  tick()\n")
        )
        views = compile_source(source)
        machine = views["state"]["machines"][0]
        for transition in machine["transitions"]:
            self.assertIsNone(transition["machine_action"])
            self.assertEqual(execution_bindings(transition), [])
            self.assertIsNone(transition["display_action"])

    def test_divergent_system_actions_remain_separate_bindings(self) -> None:
        source = DIRECT_ACTUATOR_SOURCE.replace(
            "system DoorControl\n  entry control\n",
            "system DoorControl\n  entry control\n",
        ).replace(
            "!actuator(state:DoorState):Receipt\n",
            "!actuator(state:DoorState):Receipt\n!audit(state:DoorState):Receipt\n",
        ) + """

system DoorAudit
  entry audit_control

  in state:DoorState
  in input:Input
  out receipt:Receipt

  state -> audit_control
  input -> audit_control
  audit_control -> receipt
  audit_control -> audit

>audit_control(state:DoorState,input:Input):Receipt
  next := step(state,input)
  audit(next)
"""
        views = compile_source(source)
        machine = views["state"]["machines"][0]
        opening = next(
            item for item in machine["transitions"] if item["target_state"] == "Opening"
        )
        bindings = execution_bindings(opening)
        self.assertEqual(
            {(item["system"], _display(item["action"])) for item in bindings},
            {
                ("DoorControl", "actuator(DoorState(Opening))"),
                ("DoorAudit", "audit(DoorState(Opening))"),
            },
        )
        self.assertIsNone(opening["machine_action"])
        self.assertIsNone(opening["display_action"])
        self.assertTrue(opening["action_scope"]["context_required"])
        self.assertTrue(
            any(
                item.get("code") == "STIR_SYSTEM_ACTION_CONTEXT_REQUIRED"
                for item in machine["diagnostics"]
            )
        )

    def test_multiple_transition_calls_are_diagnosed_not_collapsed(self) -> None:
        source = DIRECT_ACTUATOR_SOURCE.replace(
            "  next := step(state,input)\n  actuator(next)\n",
            "  first := step(state,input)\n  second := step(first,input)\n  actuator(second)\n",
        )
        views = compile_source(source)
        machine = views["state"]["machines"][0]
        self.assertTrue(
            any(
                item.get("code") == "STIR_SYSTEM_ACTION_MULTIPLE_TRANSITION_CALLS"
                for item in machine["diagnostics"]
            )
        )
        self.assertTrue(
            all(not execution_bindings(item) for item in machine["transitions"])
        )

    def test_target_state_is_never_action_fallback(self) -> None:
        views = compile_example("examples/state_diagrams/session_protocol.glyph")
        machine = views["state"]["machines"][0]
        for transition in machine["transitions"]:
            action = action_display(transition)
            if action:
                self.assertNotEqual(action, transition["target_state"])
            else:
                self.assertIsNone(transition["display_action"])


if __name__ == "__main__":
    unittest.main()

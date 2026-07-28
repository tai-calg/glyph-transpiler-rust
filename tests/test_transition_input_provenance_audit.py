from __future__ import annotations

import unittest
from pathlib import Path

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views


ROOT = Path(__file__).resolve().parents[1]
_UNRESOLVED = "STIR_INPUT_PREIMAGE_UNRESOLVED"


def compile_source(source: str, name: str = "audit.glyph") -> dict[str, object]:
    output = CompilationPipeline().compile_text(source, source_name=name)
    return build_io_state_views(output.model, output.diagrams.ir)


def compile_example(relative: str) -> dict[str, object]:
    path = ROOT / relative
    return compile_source(path.read_text(encoding="utf-8"), str(path))


def action_display(transition: dict[str, object]) -> str:
    action = transition.get("action")
    if not isinstance(action, dict):
        return ""
    return str(action.get("display") or action.get("expression") or "")


def transition_to(machine: dict[str, object], target: str) -> dict[str, object]:
    matches = [
        item
        for item in machine["transitions"]
        if item.get("target_state") == target and not item.get("synthesized_failure")
    ]
    if not matches:
        raise AssertionError(f"missing transition to {target}")
    return matches[0]


class TransitionInputProvenanceAuditTests(unittest.TestCase):
    def assert_unresolved_is_explicit(self, machine: dict[str, object], target: str) -> None:
        item = transition_to(machine, target)
        self.assertNotIn("input_preimage", item)
        self.assertEqual(item["trigger"]["role"], "provisional-trigger")
        self.assertEqual(item["trigger"]["confidence"], "fallback")
        self.assertTrue(str(item.get("event") or "").startswith("? "))
        self.assertIn(_UNRESOLVED, {entry["code"] for entry in machine["diagnostics"]})

    def test_direct_input_examples_are_not_rewritten_as_decision_preimages(self) -> None:
        examples = (
            "examples/state_diagrams/session_protocol.glyph",
            "examples/state_diagrams/traffic_light.glyph",
            "examples/state_diagrams/conveyor_control.glyph",
            "examples/state_diagrams/effect_failure.glyph",
            "examples/state_diagrams/valve_nested_effect.glyph",
            "examples/state_diagrams/cooling_fan_effect.glyph",
            "examples/state_diagrams/dual_machines.glyph",
        )
        for relative in examples:
            with self.subTest(example=relative):
                views = compile_example(relative)
                for machine in views["state"]["machines"]:
                    self.assertEqual(machine["analysis"]["expanded_input_preimage_count"], 0)
                    self.assertEqual(machine["analysis"]["unresolved_input_preimage_count"], 0)
                    for item in machine["transitions"]:
                        action = action_display(item)
                        if action:
                            self.assertNotEqual(action, item.get("target_state"))
                        self.assertFalse(
                            item.get("input_preimage")
                            and (item.get("trigger") or {}).get("provenance")
                            != "decision-output-preimage"
                        )

    def test_effect_examples_keep_effects_outside_action(self) -> None:
        expectations = {
            "examples/state_diagrams/conveyor_control.glyph": "set_conveyor(input.speed)",
            "examples/state_diagrams/effect_failure.glyph": "write_pump(true)",
            "examples/state_diagrams/valve_nested_effect.glyph": "write_valve(true)",
        }
        for relative, expected_effect in expectations.items():
            with self.subTest(example=relative):
                machine = compile_example(relative)["state"]["machines"][0]
                matching = [
                    item
                    for item in machine["transitions"]
                    if expected_effect
                    in {effect["expression"] for effect in item.get("effect_invocations", [])}
                ]
                self.assertTrue(matching)
                self.assertTrue(all(action_display(item) != expected_effect for item in matching))

    def test_direct_event_and_intermediate_decision_are_not_partially_expanded(self) -> None:
        source = """\
machine Controller(state:ControllerState,event:Event,input:Input)
  select=state.mode
  action=state.action
  init=ControllerState(Idle,NoAction)
  next=step(state,event,input)
  success=Idle
  failure=Faulted

+Event=Start|Cancel
*Input(allow:B)
+Decision=Run|Hold
+Action=NoAction|StartMotor
+Mode=Idle|Running|Faulted
*ControllerState(mode:Mode,action:Action)

>decide(input:Input):Decision
  input.allow >> Run
  _ >> Hold

>step(state:ControllerState,event:Event,input:Input):ControllerState
  decision := decide(input)
  next :=
    event==Start&decision==Run >> ControllerState(Running,StartMotor)
    _ >> state
  ret next
"""
        machine = compile_source(source)["state"]["machines"][0]
        self.assert_unresolved_is_explicit(machine, "Running")

    def test_multiple_intermediate_decisions_are_not_partially_expanded(self) -> None:
        source = """\
machine Controller(state:ControllerState,input:Input)
  select=state.mode
  action=state.action
  init=ControllerState(Idle,NoAction)
  next=step(state,input)
  success=Idle
  failure=Faulted

*Input(go:B,permit:B)
+Route=Go|Stay
+Permission=Allowed|Denied
+Action=NoAction|StartMotor
+Mode=Idle|Running|Faulted
*ControllerState(mode:Mode,action:Action)

>choose_route(input:Input):Route
  input.go >> Go
  _ >> Stay

>choose_permission(input:Input):Permission
  input.permit >> Allowed
  _ >> Denied

>step(state:ControllerState,input:Input):ControllerState
  route_value := choose_route(input)
  permission_value := choose_permission(input)
  next :=
    route_value==Go&permission_value==Allowed >> ControllerState(Running,StartMotor)
    _ >> state
  ret next
"""
        machine = compile_source(source)["state"]["machines"][0]
        self.assert_unresolved_is_explicit(machine, "Running")

    def test_state_dependent_decision_is_not_rendered_as_pure_input(self) -> None:
        source = """\
machine Controller(state:ControllerState,input:Input)
  select=state.mode
  action=state.action
  init=ControllerState(Idle,NoAction)
  next=step(state,input)
  success=Idle
  failure=Faulted

*Input(allow:B)
+Decision=Run|Hold
+Action=NoAction|StartMotor
+Mode=Idle|Running|Faulted
*ControllerState(mode:Mode,action:Action)

>decide(state:ControllerState,input:Input):Decision
  state.mode==Idle&input.allow >> Run
  _ >> Hold

>step(state:ControllerState,input:Input):ControllerState
  decision := decide(state,input)
  next :=
    decision==Run >> ControllerState(Running,StartMotor)
    _ >> state
  ret next
"""
        machine = compile_source(source)["state"]["machines"][0]
        self.assert_unresolved_is_explicit(machine, "Running")
        item = transition_to(machine, "Running")
        self.assertNotIn("state.mode", str((item.get("trigger") or {}).get("display") or ""))

    def test_nested_decision_helper_is_downgraded_instead_of_claimed_exact(self) -> None:
        source = """\
machine Controller(state:ControllerState,input:Input)
  select=state.mode
  action=state.action
  init=ControllerState(Idle,NoAction)
  next=step(state,input)
  success=Idle
  failure=Faulted

*Input(allow:B)
+Decision=Run|Hold
+Action=NoAction|StartMotor
+Mode=Idle|Running|Faulted
*ControllerState(mode:Mode,action:Action)

>decide(input:Input):Decision
  input.allow >> Run
  _ >> Hold

>wrapper(input:Input):Decision=decide(input)

>step(state:ControllerState,input:Input):ControllerState
  decision := wrapper(input)
  next :=
    decision==Run >> ControllerState(Running,StartMotor)
    _ >> state
  ret next
"""
        machine = compile_source(source)["state"]["machines"][0]
        self.assert_unresolved_is_explicit(machine, "Running")


if __name__ == "__main__":
    unittest.main()

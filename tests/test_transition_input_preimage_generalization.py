from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views


def compile_source(source: str, name: str) -> dict[str, object]:
    output = CompilationPipeline().compile_text(source, source_name=name)
    return build_io_state_views(output.model, output.diagrams.ir)


def action_display(item: dict[str, object]) -> str:
    action = item.get("action")
    if not isinstance(action, dict):
        return ""
    return str(action.get("display") or action.get("expression") or "")


def by_action(machine: dict[str, object], action: str) -> dict[str, object]:
    matches = [
        item
        for item in machine["transitions"]
        if action_display(item) == action and not item.get("synthesized_failure")
    ]
    if not matches:
        raise AssertionError(f"missing transition with Action {action}")
    return matches[0]


class TransitionInputPreimageGeneralizationTests(unittest.TestCase):
    def test_ordered_guards_preserve_first_match_priority(self) -> None:
        source = """\
machine Controller(state:ControllerState,input:Input)
  select=state.mode
  action=state.action
  init=ControllerState(Idle,HoldAction)
  next=step(state,input)
  success=Idle
  failure=Faulted

*Input(emergency:B,request:B)
+Decision=Stop|Run|Hold
+Action=StopAction|RunAction|HoldAction
+Mode=Idle|Running|Faulted
*ControllerState(mode:Mode,action:Action)

>decide(input:Input):Decision
  input.emergency >> Stop
  input.request >> Run
  _ >> Hold

>step(state:ControllerState,input:Input):ControllerState
  decision := decide(input)
  next :=
    decision==Stop >> ControllerState(Idle,StopAction)
    decision==Run >> ControllerState(Running,RunAction)
    decision==Hold >> ControllerState(Idle,HoldAction)
    _ >> state
  next
"""
        machine = compile_source(source, "ordered.glyph")["state"]["machines"][0]

        stopped = by_action(machine, "StopAction")
        self.assertEqual(stopped["trigger"]["display"], "input.emergency")

        running = by_action(machine, "RunAction")
        run_input = running["trigger"]["display"]
        self.assertIn("input.request", run_input)
        self.assertIn("!input.emergency", run_input)
        self.assertNotEqual(run_input, "input.request")

        held = by_action(machine, "HoldAction")
        self.assertEqual(held["trigger"]["display"], "otherwise")
        exact = held["input_preimage"]["exact_expression"]
        self.assertIn("input.emergency", exact)
        self.assertIn("input.request", exact)

    def test_local_input_chain_is_expanded_before_decision_preimage(self) -> None:
        source = """\
machine Controller(state:ControllerState,input:Input)
  select=state.mode
  action=state.action
  init=ControllerState(Idle,Stop)
  next=step(state,input)
  success=Idle
  failure=Faulted

*Input(raw:F,enabled:B)
+Command=Stop|Drive(F)
+Mode=Idle|Running|Faulted
*ControllerState(mode:Mode,action:Command)

>normalize(raw:F):F=min(raw,1.0)

>decide(speed:F,enabled:B):Command
  !enabled >> Stop
  _ >> Drive(speed)

>step(state:ControllerState,input:Input):ControllerState
  speed := normalize(input.raw)
  command := decide(speed,input.enabled)
  next :=
    command==Stop >> ControllerState(Idle,Stop)
    command==Drive(value) >> ControllerState(Running,Drive(value))
    _ >> state
  next
"""
        machine = compile_source(source, "local-chain.glyph")["state"]["machines"][0]
        drive = by_action(machine, "Drive(normalize(input.raw))")
        self.assertEqual(drive["trigger"]["display"], "otherwise")
        self.assertEqual(drive["trigger"]["provenance"], "decision-output-preimage")
        self.assertEqual(drive["action"]["value_provenance"], "decision-output-preimage")
        self.assertIn("normalize(input.raw)", drive["action"]["display"])

        stop = by_action(machine, "Stop")
        self.assertEqual(stop["trigger"]["display"], "!input.enabled")

    def test_ambiguous_payload_remains_symbolic_instead_of_being_invented(self) -> None:
        source = """\
machine Controller(state:ControllerState,input:Input)
  select=state.mode
  action=state.action
  init=ControllerState(Idle,Stop)
  next=step(state,input)
  success=Idle
  failure=Faulted

*Input(fast:B)
+Command=Stop|Drive(F)
+Mode=Idle|Running|Faulted
*ControllerState(mode:Mode,action:Command)

>decide(input:Input):Command
  input.fast >> Drive(2.0)
  _ >> Drive(1.0)

>step(state:ControllerState,input:Input):ControllerState
  command := decide(input)
  next :=
    command==Drive(speed) >> ControllerState(Running,Drive(speed))
    _ >> state
  next
"""
        machine = compile_source(source, "ambiguous-payload.glyph")["state"]["machines"][0]
        drive = by_action(machine, "Drive(speed)")
        self.assertIn("input_preimage", drive)
        self.assertNotIn("value_provenance", drive["action"])
        self.assertNotIn("Drive(1.0)", action_display(drive))
        self.assertNotIn("Drive(2.0)", action_display(drive))


if __name__ == "__main__":
    unittest.main()

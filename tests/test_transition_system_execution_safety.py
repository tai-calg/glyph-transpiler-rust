from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views


SOURCE = """system DoorControl
  entry control

  in state:DoorState
  in input:Input
  out state_out:DoorState

  state -> control
  input -> control
  control -> state_out

machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*Input(open_request:B)
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request >> DoorState(Open)
  _ >> state

>loop(value:DoorState):DoorState=loop(value)

>control(state:DoorState,input:Input):DoorState
  next := step(state,input)
  loop(next)
"""


SYNTHESIZED_FAILURE_SOURCE = """system PumpControl
  entry control

  in state:PumpState
  in event:PumpEvent
  out result:PumpState|WriteError

  state -> control
  event -> control
  control -> result
  control -> notify

machine Pump(state:PumpState,event:PumpEvent)
  select=state.mode
  init=PumpState(PumpOff,Written(false))
  next=pump_step(state,event)
  success=PumpOff
  failure=PumpFault

+PumpEvent=PumpStart|PumpStop
+PumpMode=PumpOff|PumpOn|PumpFault
+WriteError=PumpIoError
+PumpReceipt=Written(B)
*PumpState(mode:PumpMode,receipt:PumpReceipt)

!write_pump(enabled:B):PumpReceipt|WriteError
!notify(state:PumpState):PumpState

>pump_step(state:PumpState,event:PumpEvent):PumpState|WriteError
  event==PumpStart >> Ok(PumpState(PumpOn,write_pump(true)?))
  event==PumpStop >> Ok(PumpState(PumpOff,write_pump(false)?))
  _ >> Ok(state)

>control(state:PumpState,event:PumpEvent):PumpState|WriteError
  next := pump_step(state,event)?
  Ok(notify(next))
"""


def compile_source(source: str, name: str) -> dict[str, object]:
    output = CompilationPipeline().compile_text(source, source_name=name)
    return build_io_state_views(output.model, output.diagrams.ir)


class TransitionSystemExecutionSafetyTests(unittest.TestCase):
    def test_recursive_post_transition_helper_is_unresolved_not_runtime_failure(self) -> None:
        views = compile_source(SOURCE, "recursive.glyph")
        machine = views["state"]["machines"][0]
        self.assertTrue(
            any(
                item.get("code") == "STIR_SYSTEM_ACTION_UNRESOLVED"
                for item in machine["diagnostics"]
            )
        )
        self.assertTrue(
            all(
                not transition.get("execution_action_bindings")
                for transition in machine["transitions"]
            )
        )

    def test_synthesized_failure_never_runs_caller_post_transition_actions(self) -> None:
        views = compile_source(SYNTHESIZED_FAILURE_SOURCE, "failure-caller.glyph")
        machine = views["state"]["machines"][0]
        normal = [
            transition
            for transition in machine["transitions"]
            if not transition.get("synthesized_failure")
            and transition.get("execution_action_bindings")
        ]
        self.assertTrue(normal)
        self.assertTrue(
            any(
                invocation.get("operation") == "notify"
                for transition in normal
                for binding in transition["execution_action_bindings"]
                for invocation in binding.get("action_invocations", [])
            )
        )
        failures = [
            transition
            for transition in machine["transitions"]
            if transition.get("synthesized_failure")
        ]
        self.assertTrue(failures)
        for transition in failures:
            self.assertEqual(transition.get("execution_action_bindings"), [])
            self.assertEqual(transition.get("execution_contexts"), [])
            self.assertFalse(
                any(
                    invocation.get("operation") == "notify"
                    for invocation in transition.get("action_invocations", [])
                )
            )

    def test_state_specialization_requires_explicit_current_state_wiring(self) -> None:
        source = SOURCE.replace("in state:DoorState", "in previous:DoorState")
        source = source.replace("state -> control", "previous -> control")
        source = source.replace(
            ">control(state:DoorState,input:Input):DoorState\n"
            "  next := step(state,input)\n",
            ">control(previous:DoorState,input:Input):DoorState\n"
            "  next := step(previous,input)\n",
        )
        views = compile_source(source, "unproven-state.glyph")
        machine = views["state"]["machines"][0]
        self.assertTrue(
            any(
                item.get("code") == "STIR_SYSTEM_STATE_INPUT_UNPROVEN"
                for item in machine["diagnostics"]
            )
        )
        bindings = [
            binding
            for transition in machine["transitions"]
            for binding in transition.get("execution_action_bindings", [])
        ]
        self.assertTrue(bindings)
        self.assertTrue(all(binding.get("status") == "unresolved" for binding in bindings))
        self.assertTrue(all(binding.get("action") is None for binding in bindings))
        self.assertTrue(all(not binding.get("action_invocations") for binding in bindings))


if __name__ == "__main__":
    unittest.main()

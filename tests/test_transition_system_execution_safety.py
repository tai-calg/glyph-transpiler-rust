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
  out result:PumpState

  state -> control
  event -> control
  control -> result
  control -> notify
  control -> write_pump

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


UNPROVEN_STATE_SOURCE = """system DoorObserve
  entry control

  in previous:DoorState
  in input:Input
  out state_out:DoorState

  previous -> control
  input -> control
  control -> state_out
  control -> actuator

machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*Input(open_request:B)
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)

!actuator(state:DoorState):DoorState

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request >> DoorState(Open)
  _ >> state

>control(previous:DoorState,input:Input):DoorState
  next := step(previous,input)
  actuator(next)
"""


UNPROVEN_CALL_ARGUMENT_SOURCE = """system DoorControl
  entry control

  in state:DoorState
  in input:Input
  out state_out:DoorState

  state -> control
  input -> control
  control -> state_out
  control -> actuator

machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*Input(open_request:B)
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)

!actuator(state:DoorState):DoorState

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request >> DoorState(Open)
  _ >> state

>control(state:DoorState,input:Input):DoorState
  next := step(DoorState(Closed),input)
  actuator(next)
"""


UNPROVEN_INPUT_ARGUMENT_SOURCE = """system DoorControl
  entry control

  in state:DoorState
  in input:Input
  out state_out:DoorState

  state -> control
  input -> control
  control -> state_out
  control -> actuator

machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*Input(open_request:B)
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)

!actuator(state:DoorState):DoorState

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request >> DoorState(Open)
  _ >> state

>control(state:DoorState,input:Input):DoorState
  next := step(state,Input(false))
  actuator(next)
"""


PROVEN_ALIAS_CALL_SOURCE = """system DoorControl
  entry control

  in state:DoorState
  in input:Input
  out state_out:DoorState

  state -> control
  input -> control
  control -> state_out
  control -> actuator

machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*Input(open_request:B)
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)

!actuator(state:DoorState):DoorState

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request >> DoorState(Open)
  _ >> state

>control(state:DoorState,input:Input):DoorState
  current := state
  event := input
  next := step(current,event)
  actuator(next)
"""



SWAPPED_INPUT_ARGUMENT_SOURCE = """system DoorControl
  entry control

  in state:DoorState
  in event:Signal
  in mode:Signal
  out state_out:DoorState

  state -> control
  event -> control
  mode -> control
  control -> state_out
  control -> actuator

machine Door(state:DoorState,event:Signal,mode:Signal)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,event,mode)
  success=Open
  failure=Alarm

+Signal=Active|Inactive
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)

!actuator(state:DoorState):DoorState

>step(state:DoorState,event:Signal,mode:Signal):DoorState
  state.mode==Closed&event==Active >> DoorState(Open)
  state.mode==Closed&mode==Active >> DoorState(Alarm)
  _ >> state

>control(state:DoorState,event:Signal,mode:Signal):DoorState
  next := step(state,mode,event)
  actuator(next)
"""


UNWIRED_INPUT_ARGUMENT_SOURCE = """system DoorControl
  entry control

  in state:DoorState
  out state_out:DoorState

  state -> control
  control -> state_out
  control -> actuator

machine Door(state:DoorState,event:Signal)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,event)
  success=Open
  failure=Alarm

+Signal=Active|Inactive
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)

!actuator(state:DoorState):DoorState

>step(state:DoorState,event:Signal):DoorState
  state.mode==Closed&event==Active >> DoorState(Open)
  _ >> state

>control(state:DoorState,event:Signal):DoorState
  next := step(state,event)
  actuator(next)
"""


def multiple_state_source(*, wire_current_state: bool) -> str:
    state_port = "  in state:DoorState\n" if wire_current_state else ""
    state_edge = "  state -> control\n" if wire_current_state else ""
    return f"""system DoorCompare
  entry control

{state_port}  in previous:DoorState
  in input:Input
  out state_out:DoorState

{state_edge}  previous -> control
  input -> control
  control -> state_out
  control -> actuator

machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*Input(open_request:B)
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)

!actuator(state:DoorState):DoorState

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request >> DoorState(Open)
  _ >> state

>control(state:DoorState,previous:DoorState,input:Input):DoorState
  next := step(state,input)
  actuator(next)
"""

def compile_source(source: str, name: str) -> dict[str, object]:
    output = CompilationPipeline().compile_text(source, source_name=name)
    return build_io_state_views(output.model, output.diagrams.ir)


def all_contexts(machine: dict[str, object]) -> list[dict[str, object]]:
    return [
        context
        for transition in machine["transitions"]
        for context in transition.get("execution_contexts", [])
    ]


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
        views = compile_source(UNPROVEN_STATE_SOURCE, "unproven-state.glyph")
        machine = views["state"]["machines"][0]
        self.assertTrue(
            any(
                item.get("code") == "STIR_SYSTEM_STATE_INPUT_UNPROVEN"
                for item in machine["diagnostics"]
            )
        )
        contexts = all_contexts(machine)
        self.assertTrue(contexts)
        self.assertTrue(all(context.get("status") == "unresolved" for context in contexts))
        self.assertTrue(all(context.get("action") is None for context in contexts))
        self.assertTrue(all(not context.get("action_invocations") for context in contexts))
        self.assertTrue(
            all(
                transition.get("display_action") is None
                for transition in machine["transitions"]
            )
        )

    def test_machine_call_requires_original_argument_provenance(self) -> None:
        views = compile_source(UNPROVEN_CALL_ARGUMENT_SOURCE, "unproven-call-args.glyph")
        machine = views["state"]["machines"][0]
        self.assertTrue(
            any(
                item.get("code") == "STIR_SYSTEM_TRANSITION_ARGUMENT_UNPROVEN"
                for item in machine["diagnostics"]
            )
        )
        contexts = all_contexts(machine)
        self.assertTrue(contexts)
        self.assertTrue(all(context.get("status") == "unresolved" for context in contexts))
        self.assertTrue(all(context.get("action") is None for context in contexts))
        self.assertTrue(all(not context.get("action_invocations") for context in contexts))
        self.assertTrue(
            all(
                transition.get("display_action") is None
                for transition in machine["transitions"]
            )
        )

    def test_machine_call_requires_original_input_argument_provenance(self) -> None:
        views = compile_source(UNPROVEN_INPUT_ARGUMENT_SOURCE, "unproven-input-args.glyph")
        machine = views["state"]["machines"][0]
        self.assertTrue(
            any(
                item.get("code") == "STIR_SYSTEM_TRANSITION_ARGUMENT_UNPROVEN"
                for item in machine["diagnostics"]
            )
        )
        contexts = all_contexts(machine)
        self.assertTrue(contexts)
        self.assertTrue(all(context.get("status") == "unresolved" for context in contexts))
        self.assertTrue(all(context.get("action") is None for context in contexts))

    def test_aliases_preserve_machine_call_argument_provenance(self) -> None:
        views = compile_source(PROVEN_ALIAS_CALL_SOURCE, "proven-call-aliases.glyph")
        machine = views["state"]["machines"][0]
        self.assertFalse(
            any(
                item.get("code") == "STIR_SYSTEM_TRANSITION_ARGUMENT_UNPROVEN"
                for item in machine["diagnostics"]
            )
        )
        contexts = all_contexts(machine)
        self.assertTrue(contexts)
        self.assertTrue(all(context.get("status") != "unresolved" for context in contexts))
        self.assertTrue(
            any(
                context.get("action") is not None
                and "actuator(" in context["action"].get("display", "")
                for context in contexts
            )
        )


    def test_named_current_state_requires_wiring_with_other_state_values(self) -> None:
        views = compile_source(
            multiple_state_source(wire_current_state=False),
            "unproven-multiple-state.glyph",
        )
        machine = views["state"]["machines"][0]
        self.assertTrue(
            any(
                item.get("code") == "STIR_SYSTEM_STATE_INPUT_UNPROVEN"
                for item in machine["diagnostics"]
            )
        )
        contexts = all_contexts(machine)
        self.assertTrue(contexts)
        self.assertTrue(all(context.get("status") == "unresolved" for context in contexts))
        self.assertTrue(all(context.get("action") is None for context in contexts))

    def test_named_current_state_is_specialized_with_other_state_values(self) -> None:
        views = compile_source(
            multiple_state_source(wire_current_state=True),
            "proven-multiple-state.glyph",
        )
        machine = views["state"]["machines"][0]
        self.assertFalse(
            any(
                item.get("code") == "STIR_SYSTEM_STATE_INPUT_UNPROVEN"
                for item in machine["diagnostics"]
            )
        )
        contexts = all_contexts(machine)
        self.assertTrue(contexts)
        self.assertTrue(all(context.get("status") != "unresolved" for context in contexts))
        self.assertTrue(
            any(
                context.get("action") is not None
                and "actuator(DoorState(Open))" in context["action"].get("display", "")
                for context in contexts
            )
        )


    def test_machine_inputs_cannot_be_swapped_by_position(self) -> None:
        views = compile_source(SWAPPED_INPUT_ARGUMENT_SOURCE, "swapped-inputs.glyph")
        machine = views["state"]["machines"][0]
        self.assertTrue(
            any(
                item.get("code") == "STIR_SYSTEM_TRANSITION_ARGUMENT_UNPROVEN"
                for item in machine["diagnostics"]
            )
        )
        contexts = all_contexts(machine)
        self.assertTrue(contexts)
        self.assertTrue(all(context.get("status") == "unresolved" for context in contexts))
        self.assertTrue(all(context.get("action") is None for context in contexts))

    def test_machine_input_requires_explicit_system_wiring(self) -> None:
        views = compile_source(UNWIRED_INPUT_ARGUMENT_SOURCE, "unwired-input.glyph")
        machine = views["state"]["machines"][0]
        self.assertTrue(
            any(
                item.get("code") == "STIR_SYSTEM_TRANSITION_ARGUMENT_UNPROVEN"
                for item in machine["diagnostics"]
            )
        )
        contexts = all_contexts(machine)
        self.assertTrue(contexts)
        self.assertTrue(all(context.get("status") == "unresolved" for context in contexts))
        self.assertTrue(all(context.get("action") is None for context in contexts))


if __name__ == "__main__":
    unittest.main()

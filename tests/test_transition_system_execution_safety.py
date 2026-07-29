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


class TransitionSystemExecutionSafetyTests(unittest.TestCase):
    def test_recursive_post_transition_helper_is_unresolved_not_runtime_failure(self) -> None:
        output = CompilationPipeline().compile_text(SOURCE, source_name="recursive.glyph")
        views = build_io_state_views(output.model, output.diagrams.ir)
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


if __name__ == "__main__":
    unittest.main()

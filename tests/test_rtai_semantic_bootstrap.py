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
  event := input
  next := step(state,event)
  actuator(next)
"""


class RtaiSemanticBootstrapTests(unittest.TestCase):
    def test_pipeline_publishes_relation_teir_and_call_preimages_in_shadow_mode(self) -> None:
        output = CompilationPipeline().compile_text(
            SOURCE,
            source_name="rtai-bootstrap.glyph",
        )
        views = build_io_state_views(output.model, output.diagrams.ir)
        machine = views["state"]["machines"][0]
        bootstrap = machine["rtai_semantic_bootstrap"]
        self.assertEqual(bootstrap["version"], 1)
        self.assertFalse(bootstrap["projection_source"])
        self.assertEqual(bootstrap["lowering_issues"], [])
        self.assertEqual(machine["analysis"]["rtai_teir_lowering_issue_count"], 0)
        self.assertEqual(
            bootstrap["machine_relation"]["transition_function"],
            "step",
        )
        self.assertEqual(len(bootstrap["machine_relation"]["edges"]), 2)
        self.assertEqual(
            [item["function_id"] for item in bootstrap["functions"]],
            ["control", "step"],
        )
        self.assertEqual(len(bootstrap["transition_call_preimages"]), 1)
        call = bootstrap["transition_call_preimages"][0]
        self.assertEqual(call["function"], "control")
        self.assertEqual(call["target"], "next")
        self.assertEqual(call["alias_resolution"], "block-local")
        self.assertIn("NameExpr(name='input')", call["actual_arguments"][1])
        self.assertNotIn("NameExpr(name='event')", call["actual_arguments"][1])
        self.assertEqual(len(call["preimage"]["edges"]), 2)
        self.assertFalse(machine["analysis"]["rtai_semantic_bootstrap_is_projection_source"])
        self.assertEqual(views["rtai_semantic_bootstrap_version"], 1)


if __name__ == "__main__":
    unittest.main()

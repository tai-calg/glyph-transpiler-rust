from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views
from glyph.transition_analysis import (
    VerifiedEffectContractRegistry,
    build_strict_io_state_views,
    read_only_identity_contract,
)


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
  next := step(state,input)
  observed := actuator(next)
  observed
"""


class SemanticStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.output = CompilationPipeline().compile_text(
            SOURCE,
            source_name="semantic-status.glyph",
        )
        cls.contracts = VerifiedEffectContractRegistry(
            defaults=(
                (
                    "actuator",
                    read_only_identity_contract(
                        "actuator",
                        "state",
                        source="tests: reviewed identity actuator",
                    ),
                ),
            )
        )

    def test_shadow_pipeline_publishes_unresolved_status_without_claiming_exact(self) -> None:
        views = build_io_state_views(
            self.output.model,
            self.output.diagrams.ir,
        )
        statuses = [
            transition["rtai_semantic_status"]["status"]
            for machine in views["state"]["machines"]
            for transition in machine["transitions"]
        ]
        self.assertTrue(statuses)
        self.assertTrue(set(statuses).issubset({"may", "unknown"}))
        self.assertEqual(views["summary"]["rtai_semantic_exact_transition_count"], 0)

    def test_strict_contract_backed_pipeline_marks_every_transition_exact(self) -> None:
        views = build_strict_io_state_views(
            self.output.model,
            self.output.diagrams.ir,
            self.contracts,
        )
        statuses = [
            transition["rtai_semantic_status"]
            for machine in views["state"]["machines"]
            for transition in machine["transitions"]
        ]
        self.assertTrue(statuses)
        self.assertTrue(all(item["status"] == "exact" for item in statuses))
        self.assertTrue(all(item["projection_ready"] for item in statuses))
        self.assertEqual(
            views["summary"]["rtai_semantic_exact_transition_count"],
            len(statuses),
        )
        self.assertEqual(views["summary"]["rtai_semantic_unknown_transition_count"], 0)


if __name__ == "__main__":
    unittest.main()

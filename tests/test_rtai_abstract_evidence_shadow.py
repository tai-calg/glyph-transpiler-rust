from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views
from glyph.transition_analysis.abstract_evidence_shadow import (
    attach_rtai_abstract_execution_evidence,
)
from glyph.transition_analysis.native_projection_readiness import (
    attach_native_evidence_projection_readiness,
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


class AbstractEvidenceShadowTests(unittest.TestCase):
    def test_native_abstract_evidence_is_parallel_and_not_projection_source(self) -> None:
        output = CompilationPipeline().compile_text(
            SOURCE,
            source_name="abstract-evidence-shadow.glyph",
        )
        views = build_io_state_views(output.model, output.diagrams.ir)
        original = views["state"]["machines"][0]
        result = attach_rtai_abstract_execution_evidence(output.model, original)
        payload = result["rtai_abstract_execution_evidence_v2"]
        self.assertFalse(payload["projection_source"])
        self.assertEqual(len(payload["edges"]), 2)
        self.assertEqual(
            len(payload["view_edges"]),
            len(result["transitions"]),
        )
        self.assertEqual(
            result["analysis"]["rtai_abstract_execution_evidence_context_count"],
            2,
        )
        self.assertEqual(
            result["analysis"]["rtai_abstract_execution_exact_projection_count"],
            0,
        )
        self.assertEqual(result.get("display_action"), original.get("display_action"))
        for edge in payload["edges"]:
            self.assertEqual(len(edge["contexts"]), 1)
            self.assertFalse(edge["exact_action_projection_checks"][0]["allowed"])
        for transition in result["transitions"]:
            self.assertIn("rtai_execution_evidence_v2", transition)
            evidence = transition["rtai_execution_evidence_v2"]
            self.assertEqual(evidence["edge_id"], transition["id"])
            self.assertIsNotNone(evidence["analysis_edge_id"])
            self.assertEqual(
                evidence["view_edge_specialization_status"],
                "exact",
            )

    def test_native_readiness_rejects_missing_replay_witnesses(self) -> None:
        output = CompilationPipeline().compile_text(
            SOURCE,
            source_name="abstract-evidence-readiness.glyph",
        )
        views = build_io_state_views(output.model, output.diagrams.ir)
        machine = views["state"]["machines"][0]
        result = attach_native_evidence_projection_readiness(machine)
        report = result["rtai_native_evidence_projection_readiness"]
        self.assertFalse(report["ready"])
        self.assertEqual(
            report["relevant_transition_count"],
            len(result["transitions"]),
        )
        self.assertTrue(
            all(not item["ready"] for item in report["transitions"])
        )
        self.assertFalse(
            result["analysis"]["rtai_native_evidence_projection_ready"]
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.transition_analysis.abstract_solver import AbstractInterpreter
from glyph.transition_analysis.analysis_evidence import (
    AbstractEvidenceContext,
    context_evidence_from_analysis,
)
from glyph.transition_analysis.effect_summary import identity_effect_summary
from glyph.transition_analysis.exactness import (
    Approximation,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)
from glyph.transition_analysis.projection import check_exact_action_projection


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


def exact_effect() -> Approximation:
    return Approximation.exact(
        ExactnessProof(
            ExactnessProofKind.STRUCTURAL_IDENTITY,
            ExactnessProofScope.EFFECT_TRACE,
            "verified read-only identity actuator",
        )
    )


class AnalysisEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = CompilationPipeline().compile_text(
            SOURCE,
            source_name="analysis-evidence.glyph",
        ).model
        cls.analysis = AbstractInterpreter(
            cls.model,
            effect_summaries={
                "actuator": identity_effect_summary(
                    "actuator",
                    "state",
                    approximation=exact_effect(),
                )
            },
        ).analyze("control")
        cls.edge_id = cls.analysis.completed[0].transition_trace[0].edge_id

    def test_missing_witness_does_not_promote_reachability(self) -> None:
        evidence = context_evidence_from_analysis(
            self.analysis,
            AbstractEvidenceContext(
                self.edge_id,
                "DoorControl",
                "control",
            ),
        ).to_ir()
        self.assertEqual(evidence["reachability"]["status"], "may-reachable")
        decision = check_exact_action_projection(evidence)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "reachability-is-not-proven")
        self.assertEqual(
            evidence["cardinality"]["upper_bound"],
            "at-most-one",
        )

    def test_concrete_edge_witness_allows_property_scoped_exact_projection(self) -> None:
        evidence = context_evidence_from_analysis(
            self.analysis,
            AbstractEvidenceContext(
                self.edge_id,
                "DoorControl",
                "control",
                witness={"edge_id": self.edge_id, "source": "bounded-oracle"},
            ),
        ).to_ir()
        decision = check_exact_action_projection(evidence)
        self.assertTrue(decision.allowed, decision.reason)
        self.assertIsNotNone(decision.action)
        assert decision.action is not None
        self.assertEqual(decision.action["kind"], "effect-trace")

    def test_unknown_effect_summary_remains_rejected(self) -> None:
        analysis = AbstractInterpreter(self.model).analyze("control")
        edge_id = analysis.completed[0].transition_trace[0].edge_id
        evidence = context_evidence_from_analysis(
            analysis,
            AbstractEvidenceContext(
                edge_id,
                "DoorControl",
                "control",
                witness={"edge_id": edge_id},
            ),
        ).to_ir()
        decision = check_exact_action_projection(evidence)
        self.assertFalse(decision.allowed)
        self.assertIn(
            decision.reason,
            {
                "effect-trace-is-not-exact",
                "completion-is-not-exact",
                "unknown-reasons-are-present",
            },
        )


if __name__ == "__main__":
    unittest.main()

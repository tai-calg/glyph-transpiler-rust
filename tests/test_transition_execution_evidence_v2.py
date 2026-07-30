from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views
from glyph.transition_analysis.exactness import (
    Approximation,
    ApproximationCause,
    ApproximationKind,
    ExactnessProof,
    ExactnessProofKind,
)
from glyph.transition_analysis.legacy_shadow import attach_execution_evidence_v2
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
  actuator(next)
"""


class ApproximationSafetyTests(unittest.TestCase):
    def test_exact_requires_explicit_proof(self) -> None:
        with self.assertRaises(ValueError):
            Approximation.exact()

    def test_join_never_recovers_exactness_after_precision_loss(self) -> None:
        exact = Approximation.exact(
            ExactnessProof(
                ExactnessProofKind.STRUCTURAL_IDENTITY,
                "unit-test structural identity",
            )
        )
        widened = exact.degrade(ApproximationCause.WIDENING)
        joined = Approximation.combine((exact, widened))
        self.assertEqual(joined.kind, ApproximationKind.OVER_APPROXIMATE)
        self.assertIn(ApproximationCause.WIDENING.value, joined.causes)
        self.assertFalse(joined.is_exact)

    def test_unknown_dominates_join(self) -> None:
        over = Approximation.over_approximate(ApproximationCause.LEGACY_ADAPTER)
        unknown = Approximation.unknown(ApproximationCause.SOLVER_UNKNOWN)
        joined = Approximation.combine((over, unknown))
        self.assertEqual(joined.kind, ApproximationKind.UNKNOWN)
        self.assertIn(ApproximationCause.LEGACY_ADAPTER.value, joined.causes)
        self.assertIn(ApproximationCause.SOLVER_UNKNOWN.value, joined.causes)


class ExactActionProjectionTests(unittest.TestCase):
    def test_legacy_shadow_evidence_is_never_exactly_projected(self) -> None:
        machine = {
            "transitions": [
                {
                    "source_state": "Closed",
                    "target_state": "Open",
                    "execution_action_bindings": [
                        {
                            "scope": "system",
                            "system": "DoorControl",
                            "entry": "control",
                            "status": "resolved",
                            "transition_call_count": 1,
                            "action": {"display": "actuator(Open)"},
                            "action_cases": [
                                {
                                    "condition": None,
                                    "outcome": "success",
                                    "reaches_continuation": True,
                                    "effect_invocations": [
                                        {
                                            "operation": "actuator",
                                            "expression": "actuator(Open)",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        evidenced = attach_execution_evidence_v2(machine)
        evidence = evidenced["transitions"][0]["execution_evidence_v2"]
        context = evidence["contexts"][0]
        decision = check_exact_action_projection(context)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "reachability-is-not-proven")
        self.assertEqual(context["effect_trace"]["approximation"]["kind"], "over-approximate")

    def test_checker_accepts_only_fully_proven_singleton_action(self) -> None:
        proof = Approximation.exact(
            ExactnessProof(
                ExactnessProofKind.EXHAUSTIVE_FINITE_ORACLE,
                "all finite input combinations matched the concrete interpreter",
            )
        ).to_ir()
        context = {
            "reachability": {
                "status": "proven-reachable",
                "witness": {"input": "OpenRequest"},
                "approximation": proof,
            },
            "cardinality": {
                "upper_bound": "at-most-one",
                "witness": {"count": 1},
                "approximation": proof,
            },
            "effect_trace": {
                "alternatives": [
                    {
                        "condition": None,
                        "events": [
                            {
                                "operation": "actuator",
                                "expression": "actuator(Open)",
                            }
                        ],
                    }
                ],
                "is_singleton": True,
                "approximation": proof,
            },
            "completion": {
                "kinds": ["normal"],
                "approximation": proof,
            },
            "unknown_reasons": [],
            "legacy_action": {"display": "actuator(Open)"},
        }
        decision = check_exact_action_projection(context)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.action, {"display": "actuator(Open)"})

    def test_synthesized_failure_has_no_caller_context(self) -> None:
        machine = {
            "transitions": [
                {
                    "source_state": "PumpOn",
                    "target_state": "PumpFault",
                    "synthesized_failure": True,
                    "execution_action_bindings": [],
                    "execution_contexts": [],
                }
            ]
        }
        evidenced = attach_execution_evidence_v2(machine)
        evidence = evidenced["transitions"][0]["execution_evidence_v2"]
        self.assertEqual(evidence["contexts"], [])
        self.assertEqual(evidence["completion"]["kinds"], ["no-continuation"])
        self.assertEqual(evidence["exact_action_projection_checks"], [])


class EvidencePipelineIntegrationTests(unittest.TestCase):
    def test_public_pipeline_publishes_shadow_evidence_without_using_it_for_projection(self) -> None:
        output = CompilationPipeline().compile_text(SOURCE, source_name="evidence-v2.glyph")
        views = build_io_state_views(output.model, output.diagrams.ir)
        machine = views["state"]["machines"][0]
        self.assertFalse(machine["analysis"]["execution_evidence_v2_is_projection_source"])
        self.assertEqual(machine["analysis"]["execution_evidence_v2_version"], 2)
        self.assertTrue(
            all(
                "execution_evidence_v2" in transition
                for transition in machine["transitions"]
            )
        )
        self.assertTrue(
            all(
                not check.get("allowed")
                for transition in machine["transitions"]
                for check in transition["execution_evidence_v2"].get(
                    "exact_action_projection_checks", []
                )
            )
        )


if __name__ == "__main__":
    unittest.main()

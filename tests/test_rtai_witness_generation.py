from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views
from glyph.transition_analysis import (
    VerifiedEffectContractRegistry,
    attach_native_evidence_projection_readiness,
    attach_rtai_abstract_execution_evidence,
    generate_bounded_system_witnesses,
    read_only_identity_contract,
)
from glyph.transition_analysis.strict_projection_campaign import (
    build_strict_io_state_views,
    build_strict_projection_candidate,
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


class WitnessGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        output = CompilationPipeline().compile_text(
            SOURCE,
            source_name="witness-generation.glyph",
        )
        cls.model = output.model
        cls.execution = output.diagrams.ir
        cls.views = build_io_state_views(output.model, output.diagrams.ir)
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

    def test_finite_system_entry_generates_same_edge_witnesses(self) -> None:
        report = generate_bounded_system_witnesses(
            self.model,
            ("control",),
            self.contracts,
        )
        self.assertTrue(report.complete, report.issues)
        self.assertEqual(report.attempted_case_count, 6)
        self.assertEqual(report.completed_case_count, 6)
        self.assertEqual(
            {item.completion for item in report.witnesses},
            {"returned"},
        )
        self.assertEqual(len({item.edge_id for item in report.witnesses}), 2)

    def test_contract_backed_native_evidence_passes_readiness(self) -> None:
        machine = self.views["state"]["machines"][0]
        evidenced = attach_rtai_abstract_execution_evidence(
            self.model,
            machine,
            effect_contracts=self.contracts,
        )
        payload = evidenced["rtai_abstract_execution_evidence_v2"]
        self.assertTrue(payload["witness_generation"]["complete"])
        self.assertEqual(payload["witness_generation"]["witness_count"], 2)
        self.assertTrue(evidenced["analysis"]["rtai_effect_contracts_configured"])

        audited = attach_native_evidence_projection_readiness(evidenced)
        report = audited["rtai_native_evidence_projection_readiness"]
        self.assertTrue(report["ready"], report)
        self.assertTrue(all(item["ready"] for item in report["transitions"]))

    def test_strict_candidate_uses_only_native_evidence_actions(self) -> None:
        machine = self.views["state"]["machines"][0]
        result = build_strict_projection_candidate(
            self.model,
            machine,
            self.contracts,
        )
        campaign = result["strict_projection_campaign"]
        self.assertTrue(campaign["ready"], campaign)
        self.assertFalse(campaign["legacy_fallback_allowed"])
        for transition in result["transitions"]:
            self.assertFalse(transition["legacy_system_action_fallback_allowed"])
            self.assertEqual(transition["execution_action_bindings"], [])
            self.assertEqual(transition["execution_contexts"], [])
            self.assertEqual(
                transition["strict_system_action_projection_source"],
                "rtai-execution-evidence-v2",
            )
            self.assertIsNotNone(transition["strict_system_action"])
            self.assertEqual(
                transition["system_action"],
                transition["strict_system_action"],
            )

    def test_strict_full_view_campaign_is_ready_without_legacy_analyzer(self) -> None:
        result = build_strict_io_state_views(
            self.model,
            self.execution,
            self.contracts,
        )
        campaign = result["strict_projection_campaign"]
        self.assertTrue(campaign["ready"], campaign)
        self.assertFalse(campaign["legacy_fallback_allowed"])
        self.assertFalse(campaign["legacy_system_action_analyzer_enabled"])
        self.assertFalse(result["rtai_legacy_system_action_analyzer_enabled"])
        self.assertFalse(
            result["summary"]["rtai_legacy_system_action_analyzer_enabled"]
        )
        self.assertEqual(
            result["summary"]["rtai_strict_projection_ready_machines"],
            1,
        )
        for machine in result["state"]["machines"]:
            self.assertTrue(machine["strict_projection_campaign"]["ready"])
            self.assertFalse(
                machine["analysis"]["rtai_strict_projection_legacy_analyzer_enabled"]
            )
            for transition in machine["transitions"]:
                self.assertFalse(transition["legacy_system_action_fallback_allowed"])
                self.assertNotIn("execution_evidence_v2", transition)
                self.assertEqual(transition.get("execution_action_bindings", []), [])
                self.assertEqual(transition.get("execution_contexts", []), [])

    def test_strict_candidate_fails_closed_without_effect_contract(self) -> None:
        machine = self.views["state"]["machines"][0]
        result = build_strict_projection_candidate(
            self.model,
            machine,
            VerifiedEffectContractRegistry(),
        )
        campaign = result["strict_projection_campaign"]
        self.assertFalse(campaign["ready"])
        self.assertFalse(campaign["legacy_fallback_allowed"])
        self.assertTrue(campaign["blockers"])
        for transition in result["transitions"]:
            self.assertFalse(transition["legacy_system_action_fallback_allowed"])
            self.assertIsNone(transition["strict_system_action"])
            self.assertIsNone(transition["system_action"])

    def test_empty_contract_registry_never_infers_effect_handler(self) -> None:
        report = generate_bounded_system_witnesses(
            self.model,
            ("control",),
            VerifiedEffectContractRegistry(),
        )
        self.assertFalse(report.complete)
        self.assertEqual(report.completed_case_count, 0)
        self.assertEqual(report.witnesses, ())
        self.assertEqual(report.issues[0].code, "concrete-replay-failed")
        self.assertIn("requires an explicit concrete handler", report.issues[0].detail)


if __name__ == "__main__":
    unittest.main()

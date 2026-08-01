from __future__ import annotations

from pathlib import Path
import unittest

from glyph.compilation import CompilationPipeline
from glyph.default_workspace import DEFAULT_SOURCE
from glyph.io_state_views import build_io_state_views
from glyph.transition_analysis.evidence_projection import EvidenceProjectionMode
from glyph.transition_analysis.public_effect_contracts import (
    BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID,
    PUBLIC_STRICT_PROGRAMS,
)
from glyph.transition_analysis.semantic_event import action_event_reference_ids


ROOT = Path(__file__).resolve().parents[1]


def _builtin_default_source() -> str:
    return DEFAULT_SOURCE


def _program_source(source_id: str, source_path: str | None) -> str:
    if source_id == BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID:
        return _builtin_default_source()
    if source_path is None:
        raise AssertionError(f"source path missing for {source_id}")
    return (ROOT / source_path).read_text(encoding="utf-8")


def _normal_source_name(source_id: str, source_path: str | None) -> str:
    if source_id == BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID:
        return "/tmp/project/.glyph/workspace.glyph"
    assert source_path is not None
    return str(ROOT / source_path)


def _views(source: str, source_name: str) -> dict[str, object]:
    compiled = CompilationPipeline().compile_text(source, source_name=source_name)
    return build_io_state_views(compiled.model, compiled.diagrams.ir)


def _transitions(views: dict[str, object]) -> list[dict[str, object]]:
    return [
        transition
        for machine in views["state"]["machines"]
        for transition in machine["transitions"]
    ]


def _transition_diagnostics(transitions: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "edge_id": transition.get("edge_id") or transition.get("id"),
            "source_state": transition.get("source_state"),
            "target_state": transition.get("target_state"),
            "source": transition.get("source"),
            "condition": transition.get("condition"),
            "binding": transition.get("rtai_view_edge_specialization"),
            "status": transition.get("rtai_semantic_status"),
            "projection": transition.get("evidence_projection"),
        }
        for transition in transitions
    ]


class PublicStrictActivationTests(unittest.TestCase):
    def test_cataloged_public_contexts_use_strict_exact_in_normal_builder(self) -> None:
        self.assertGreater(len(PUBLIC_STRICT_PROGRAMS), 1)
        for program in PUBLIC_STRICT_PROGRAMS:
            with self.subTest(source=program.source_id):
                views = _views(
                    _program_source(program.source_id, program.source_path),
                    _normal_source_name(program.source_id, program.source_path),
                )
                activation = views["rtai_public_strict_activation"]
                self.assertTrue(activation["active"], activation)
                self.assertEqual(activation["source_id"], program.source_id)
                self.assertEqual(
                    views["rtai_projection_mode"],
                    EvidenceProjectionMode.STRICT_EXACT.value,
                )
                self.assertFalse(
                    views["rtai_legacy_system_action_analyzer_enabled"]
                )
                self.assertTrue(
                    views["summary"]["rtai_public_strict_activation_active"]
                )

    def test_underspecified_failure_context_remains_shadow(self) -> None:
        source_path = ROOT / "examples/acceptance/door_controller.glyph"
        views = _views(source_path.read_text(encoding="utf-8"), str(source_path))
        activation = views["rtai_public_strict_activation"]
        self.assertFalse(activation["active"], activation)
        self.assertEqual(
            views["rtai_projection_mode"],
            EvidenceProjectionMode.SHADOW.value,
        )
        self.assertTrue(views["rtai_legacy_system_action_analyzer_enabled"])

    def test_catalog_path_with_incompatible_effect_surface_remains_shadow(self) -> None:
        source = """system MotorSafety
  entry cycle

  in state:State
  out state_out:State

  state -> cycle
  cycle -> state_out

+Mode=Stopped
*State(mode:Mode)

>cycle(state:State):State=state
"""
        source_name = str(ROOT / "examples/acceptance/motor_safety.glyph")
        views = _views(source, source_name)
        self.assertFalse(views["rtai_public_strict_activation"]["active"])
        self.assertEqual(
            views["rtai_projection_mode"],
            EvidenceProjectionMode.SHADOW.value,
        )

    def test_motor_activation_supplies_reviewed_witnesses_and_nested_effects(self) -> None:
        path = ROOT / "examples/acceptance/motor_safety.glyph"
        views = _views(path.read_text(encoding="utf-8"), str(path))
        activation = views["rtai_public_strict_activation"]
        self.assertEqual(activation["targeted_witness_case_count"], 4)
        self.assertTrue(views["rtai_targeted_witnesses_configured"])

        transitions = _transitions(views)
        self.assertTrue(transitions)
        exact_transitions = [
            item
            for item in transitions
            if item["rtai_semantic_status"]["status"] == "exact"
            and not item.get("synthesized_failure")
        ]
        self.assertTrue(exact_transitions, _transition_diagnostics(transitions))
        for transition in exact_transitions:
            events = [
                event
                for context in transition["rtai_execution_evidence_v2"]["contexts"]
                for alternative in context["effect_trace"]["alternatives"]
                for event in alternative["events"]
            ]
            self.assertEqual([event["operation"] for event in events], ["write_motor"])
            self.assertEqual(
                [event["expression"] for event in events],
                [transition["machine_action"]["display"]],
            )
            self.assertNotIn("ConstantValue", events[0]["expression"])
            self.assertIsNotNone(transition.get("system_action"))
            machine_event_ids = action_event_reference_ids(
                transition["machine_action"]
            )
            system_event_ids = action_event_reference_ids(
                transition["system_action"]
            )
            self.assertEqual(len(machine_event_ids), 1)
            self.assertEqual(machine_event_ids, system_event_ids)
            self.assertEqual(
                transition["semantic_action_aliasing"]["status"],
                "proven-alias",
            )
            self.assertEqual(
                transition["machine_action_invocations"][0]["alias_of_event_id"],
                system_event_ids[0],
            )


if __name__ == "__main__":
    unittest.main()

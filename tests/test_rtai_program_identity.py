from __future__ import annotations

from pathlib import Path
import unittest

from glyph.compilation import CompilationPipeline
from glyph.transition_analysis.public_strict_activation import (
    evaluate_public_strict_activation,
)


ROOT = Path(__file__).resolve().parents[1]
MOTOR_PATH = ROOT / "examples/acceptance/motor_safety.glyph"


def _decision(source: str, source_name: str | None = None):
    compiled = CompilationPipeline().compile_text(
        source,
        source_name=source_name or str(MOTOR_PATH),
    )
    return evaluate_public_strict_activation(compiled.model, source_name or str(MOTOR_PATH))


class ProgramIdentityTests(unittest.TestCase):
    def test_exact_reviewed_artifact_activates_with_component_digests(self) -> None:
        source = MOTOR_PATH.read_text(encoding="utf-8")
        first = _decision(source)
        second = _decision(source)

        self.assertTrue(first.active, first.to_ir())
        self.assertTrue(second.active, second.to_ir())
        assert first.current_identity is not None
        assert second.current_identity is not None
        identity = first.current_identity
        self.assertEqual(identity.fingerprint, second.current_identity.fingerprint)
        self.assertEqual(len(identity.artifact_sha256), 64)
        self.assertEqual(len(identity.semantic_sha256), 64)
        self.assertEqual(len(identity.entry_signature_sha256), 64)
        self.assertEqual(len(identity.effect_declaration_sha256), 64)
        self.assertEqual(len(identity.machine_relation_sha256), 64)

    def test_same_path_and_surface_with_comment_edit_is_rejected(self) -> None:
        source = MOTOR_PATH.read_text(encoding="utf-8") + "\n# unreviewed edit\n"
        decision = _decision(source)

        self.assertFalse(decision.active)
        self.assertIn(
            "source-content-mismatch",
            {item.code for item in decision.blockers},
        )
        self.assertIsNotNone(decision.current_identity)

    def test_same_path_and_effect_signature_with_guard_edit_is_rejected(self) -> None:
        source = MOTOR_PATH.read_text(encoding="utf-8")
        edited = source.replace(
            "input.emergency >> EmergencyBrake",
            "input.emergency&input.enabled >> EmergencyBrake",
        )
        self.assertNotEqual(source, edited)
        decision = _decision(edited)

        self.assertFalse(decision.active)
        self.assertIn(
            "source-content-mismatch",
            {item.code for item in decision.blockers},
        )

    def test_unreviewed_path_returns_structured_blocker(self) -> None:
        source = MOTOR_PATH.read_text(encoding="utf-8")
        decision = _decision(source, "/tmp/unreviewed.glyph")

        self.assertFalse(decision.active)
        self.assertEqual(decision.blockers[0].code, "no-reviewed-catalog-candidate")
        self.assertIsNone(decision.current_identity)


if __name__ == "__main__":
    unittest.main()

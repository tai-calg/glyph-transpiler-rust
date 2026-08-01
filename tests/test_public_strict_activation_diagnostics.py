from __future__ import annotations

from pathlib import Path
import unittest

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views


ROOT = Path(__file__).resolve().parents[1]
MOTOR_PATH = ROOT / "examples/acceptance/motor_safety.glyph"


class PublicStrictActivationDiagnosticsTests(unittest.TestCase):
    def test_normal_views_preserve_same_path_source_mismatch_blocker(self) -> None:
        source = MOTOR_PATH.read_text(encoding="utf-8") + "\n# unreviewed edit\n"
        compiled = CompilationPipeline().compile_text(
            source,
            source_name=str(MOTOR_PATH),
        )
        views = build_io_state_views(compiled.model, compiled.diagrams.ir)
        activation = views["rtai_public_strict_activation"]

        self.assertFalse(activation["active"])
        self.assertEqual(activation["source_id"], "examples/acceptance/motor_safety.glyph")
        self.assertIn(
            "source-content-mismatch",
            {item["code"] for item in activation["blockers"]},
        )
        self.assertIsNotNone(activation["program_identity"])
        self.assertEqual(
            activation["reason"],
            "source-content-mismatch",
        )
        self.assertEqual(views["rtai_projection_mode"], "shadow")
        self.assertEqual(
            views["summary"]["rtai_public_strict_activation_blocker_count"],
            len(activation["blockers"]),
        )

    def test_unreviewed_path_preserves_candidate_absence_reason(self) -> None:
        source = MOTOR_PATH.read_text(encoding="utf-8")
        compiled = CompilationPipeline().compile_text(
            source,
            source_name="/tmp/private-copy.glyph",
        )
        views = build_io_state_views(compiled.model, compiled.diagrams.ir)
        activation = views["rtai_public_strict_activation"]

        self.assertFalse(activation["active"])
        self.assertEqual(
            activation["reason"],
            "no-reviewed-catalog-candidate",
        )
        self.assertEqual(activation["program_identity"], None)
        self.assertEqual(views["rtai_projection_mode"], "shadow")


if __name__ == "__main__":
    unittest.main()

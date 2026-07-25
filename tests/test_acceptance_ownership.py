from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glyph.studio_manual import GlyphProjectStudio
from tests.acceptance_support import EXAMPLES, compile_example, load


class AcceptanceOwnershipTests(unittest.TestCase):
    def test_motor_normalization_is_an_explicit_helper(self) -> None:
        path = EXAMPLES["motor"]
        source = path.read_text(encoding="utf-8")
        self.assertIn(">normalize(raw:F):F", source)
        self.assertNotIn("@NORMALIZE", source)

        outputs = compile_example("motor")
        self.assertIn("pub fn normalize", outputs.artifacts.logic)
        self.assertIn("pub fn decide", outputs.artifacts.logic)

        mapping = load(outputs, "preprocessor-map.json")
        self.assertFalse(
            any("NORMALIZE" in item["macro_stack"] for item in mapping["expanded_lines"])
        )

    def test_manual_rust_is_not_overwritten(self) -> None:
        source_text = EXAMPLES["batch"].read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "batch.glyph"
            source.write_text(source_text, encoding="utf-8")
            studio = GlyphProjectStudio(source)
            first = studio.rebuild()
            self.assertEqual(first.status, "ready")
            manual = studio.output_dir / "manual.rs"
            custom = "// user-owned implementation\n"
            manual.write_text(custom, encoding="utf-8")
            second = studio.rebuild(source_text + "\n# rebuild\n")
            self.assertEqual(second.status, "ready")
            self.assertEqual(manual.read_text(encoding="utf-8"), custom)
            self.assertEqual(second.artifacts["manual.rs"], custom)


if __name__ == "__main__":
    unittest.main()

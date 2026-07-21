from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glyph.studio_manual import GlyphProjectStudio
from tests.acceptance_support import EXAMPLES, compile_example, load


class AcceptanceOwnershipTests(unittest.TestCase):
    def test_motor_macro_points_to_invocation_line(self) -> None:
        path = EXAMPLES["motor"]
        lines = path.read_text(encoding="utf-8").splitlines()
        invocation = next(i for i, line in enumerate(lines, 1) if line.strip() == "NORMALIZE")
        outputs = compile_example("motor")
        algorithm = load(outputs, "algorithm-ir.json")
        decide = next(item for item in algorithm["functions"] if item["name"] == "decide")
        normalized = next(item for item in decide["steps"] if item.get("name") == "normalized")
        self.assertEqual(normalized["source"]["line"], invocation)
        mapping = load(outputs, "preprocessor-map.json")
        self.assertTrue(any("NORMALIZE" in item["macro_stack"] for item in mapping["expanded_lines"]))

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

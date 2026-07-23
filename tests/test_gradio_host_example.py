from __future__ import annotations

import ast
import unittest
from pathlib import Path

from glyph.compilation import CompilationPipeline
from glyph.pure_runtime import PureGlyphProgram, glyph_to_python


ROOT = Path(__file__).resolve().parents[1]
GLYPH_SOURCE = ROOT / "examples" / "gradio_temperature.glyph"
GRADIO_APP = ROOT / "examples" / "gradio_temperature_app.py"
REQUIREMENTS = ROOT / "requirements-gradio.txt"


class GradioHostExampleTests(unittest.TestCase):
    def test_glyph_example_compiles_and_executes(self) -> None:
        source = GLYPH_SOURCE.read_text(encoding="utf-8")
        compilation = CompilationPipeline().compile_text(
            source,
            source_name=str(GLYPH_SOURCE),
        )
        program = PureGlyphProgram(compilation.model)
        value = glyph_to_python(
            program.invoke(
                "render",
                {
                    "input": {"celsius": 36.5},
                    "session": {"count": 4},
                },
            )
        )

        self.assertAlmostEqual(value["fahrenheit"], 97.7)
        self.assertEqual(value["count"], 5)
        self.assertEqual(value["band"]["variant"], "Hot")

    def test_product_and_sum_declarations_are_closed_on_one_line(self) -> None:
        source = GLYPH_SOURCE.read_text(encoding="utf-8")
        declarations = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("*", "+"))
        ]
        self.assertTrue(declarations)
        for declaration in declarations:
            if declaration.startswith("*"):
                self.assertTrue(declaration.endswith(")"), declaration)
            self.assertNotIn("\n", declaration)

    def test_gradio_app_is_valid_python_and_uses_live_runtime(self) -> None:
        source = GRADIO_APP.read_text(encoding="utf-8")
        ast.parse(source, filename=str(GRADIO_APP))

        for marker in (
            "LivePureGlyphRuntime",
            "gr.LinePlot",
            "gr.State",
            "gr.Timer",
            "runtime.invoke",
            "TemperatureBand",
            "GLYPH × GRADIO LIVE HOST",
        ):
            self.assertIn(marker, source)

        # Business formulas remain exclusively in the .glyph source.
        self.assertNotIn("* 1.8", source)
        self.assertNotIn("273.15", source)
        self.assertNotIn("gr.get_component", source)

    def test_optional_dependencies_are_major_version_bounded(self) -> None:
        requirements = REQUIREMENTS.read_text(encoding="utf-8")
        self.assertIn("gradio>=6.0,<7", requirements)
        self.assertIn("pandas>=2.0,<3", requirements)


if __name__ == "__main__":
    unittest.main()

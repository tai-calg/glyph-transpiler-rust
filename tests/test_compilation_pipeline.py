from __future__ import annotations

import inspect
import json
import unittest
from unittest.mock import patch

import glyph.compilation as compilation
import glyph.studio as studio
import glyph.studio_ui as studio_ui
from glyph import CompilationPipeline, IncrementalCompiler
from glyph.artifacts import parse_compilation_model


SOURCE = """@LIMIT=100
system Demo
  input -> process
  process -> output

*Input(value:U)
>process(x:U):U
  limited :=
    x>LIMIT >> LIMIT
    _ >> x
  limited
!output(x:U):U
"""


class CompilationPipelineTests(unittest.TestCase):
    def test_incremental_compiler_parses_once_per_source_digest(self) -> None:
        with patch.object(
            compilation,
            "parse_compilation_model",
            wraps=parse_compilation_model,
        ) as parse:
            compiler = IncrementalCompiler()
            first = compiler.compile_text(SOURCE, "demo.glyph")
            second = compiler.compile_text(SOURCE, "demo.glyph")

        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(parse.call_count, 1)
        self.assertIs(first.snapshot, second.snapshot)

    def test_machine_readable_artifacts_have_explicit_schema_versions(self) -> None:
        outputs = CompilationPipeline().compile_text(SOURCE, "schema.glyph")
        expected = {
            "architecture-ir.json": "glyph.architecture-ir",
            "algorithm-ir.json": "glyph.algorithm-ir",
            "execution-ir.json": "glyph.execution-ir",
            "source-map.json": "glyph.source-map",
            "preprocessor-map.json": "glyph.preprocessor-map",
        }
        for filename, schema in expected.items():
            with self.subTest(filename=filename):
                payload = json.loads(outputs.diagrams.files[filename])
                self.assertEqual(payload["schema"], schema)
                self.assertEqual(payload["version"], 1)

        design = json.loads(outputs.design_json)
        self.assertEqual(design["schema"], "glyph.typed-design")
        self.assertEqual(design["version"], 1)
        self.assertEqual(
            design["architecture"]["schema"],
            "glyph.architecture-ir",
        )

    def test_studio_ui_has_one_authoritative_implementation(self) -> None:
        self.assertIs(studio.STUDIO_HTML, studio_ui.STUDIO_HTML)
        source = inspect.getsource(studio)
        self.assertNotIn("STUDIO_HTML = r", source)
        self.assertIn("from .studio_ui import STUDIO_HTML", source)
        self.assertIn("Architecture", studio.STUDIO_HTML)
        self.assertIn("Logic", studio.STUDIO_HTML)
        self.assertIn("Manual", studio.STUDIO_HTML)


if __name__ == "__main__":
    unittest.main()

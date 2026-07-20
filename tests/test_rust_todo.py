from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glyph import GlyphError, compile_artifacts, compile_source, parse_compilation_model
from glyph.studio_manual import GlyphProjectStudio


class GuardAndRustTodoTests(unittest.TestCase):
    def test_guard_chain_generates_if_else_if_else(self) -> None:
        source = """
+Kind=Negative|Zero|Positive
>classify(x:I):Kind
  x<0 >> Negative
  x==0 >> Zero
  _ >> Positive
"""
        rust = compile_source(source)
        self.assertIn("if x < 0", rust)
        self.assertIn("else if x == 0", rust)
        self.assertIn("else {", rust)

    def test_opaque_pure_function_calls_manual_rust(self) -> None:
        source = """
*Graph(nodes:U)
*Path(cost:U)
~shortest(graph:Graph,start:U,goal:U):Path # TODO: A* in Rust
>plan(graph:Graph,start:U,goal:U):Path=shortest(graph,start,goal)
"""
        artifacts = compile_artifacts(source)
        self.assertIn("crate::manual::shortest(graph, start, goal)", artifacts.logic)
        self.assertNotIn("pub fn shortest", artifacts.host)
        self.assertIn("pub fn shortest", artifacts.manual_scaffold)
        self.assertIn("TODO: A* in Rust", artifacts.manual_scaffold)

        model = parse_compilation_model(source)
        self.assertEqual(model.opaques[0].name, "shortest")
        symbol = model.semantic.symbol("shortest")
        assert symbol is not None
        self.assertEqual(symbol.kind, "rust")

    def test_opaque_function_is_a_pure_pipeline_stage(self) -> None:
        source = """
*Path(cost:U)
~optimize(path:Path):Path
>run(path:Path):Path=path /> optimize
"""
        artifacts = compile_artifacts(source)
        self.assertIn("crate::manual::optimize(path)", artifacts.logic)

    def test_opaque_body_is_rejected(self) -> None:
        source = "~bad(x:U):U=x+1\n"
        with self.assertRaisesRegex(GlyphError, "Rust側で実装"):
            compile_artifacts(source)

    def test_architecture_marks_manual_rust_component(self) -> None:
        source = """
system Planner
  input -> solve
  solve -> output

~solve(x:U):U
"""
        model = parse_compilation_model(source)
        components = model.architecture.systems[0].components
        solve = next(item for item in components if item.name == "solve")
        self.assertEqual(solve.kind, "rust")

    def test_studio_creates_manual_once_and_preserves_edits(self) -> None:
        source_text = """
~solve(x:U):U # TODO: complex algorithm
>run(x:U):U=solve(x)
"""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.glyph"
            source.write_text(source_text, encoding="utf-8")
            studio = GlyphProjectStudio(source)
            first = studio.rebuild()
            self.assertEqual(first.status, "ready")
            manual = studio.output_dir / "manual.rs"
            self.assertTrue(manual.exists())

            implementation = """use crate::generated::*;

pub fn solve(x: u16) -> u16 {
    x + 1
}
"""
            manual.write_text(implementation, encoding="utf-8")
            source.write_text(source_text + "\n# rebuild\n", encoding="utf-8")
            second = studio.rebuild()
            self.assertEqual(second.status, "ready")
            self.assertEqual(manual.read_text(encoding="utf-8"), implementation)
            self.assertEqual(second.artifacts["manual.rs"], implementation)


if __name__ == "__main__":
    unittest.main()

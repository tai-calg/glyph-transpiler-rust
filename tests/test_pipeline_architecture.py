from __future__ import annotations

import unittest

from glyph import GlyphError, compile_source, parse_compilation_model
from glyph.mermaid import compile_diagram_bundle
from glyph.pipeline import join_pipeline_continuations
from glyph.studio_ui import STUDIO_HTML


class PipelineAndArchitectureTests(unittest.TestCase):
    def test_multiline_slash_pipe_with_lambdas(self) -> None:
        source = """
@MAX=1000
*In(value:U)
+C=Run(U)
+Error=Bad
>validate(i:In):In|Error=Ok(i)
>command(n:U):C|Error=Ok(Run(n))
>ctl(i:In):C|Error=
  i
  /> validate?
  /> |x| x.value
  /> |n| min(n,MAX)
  /> command
"""
        rust = compile_source(source)
        self.assertIn("pub fn __glyph_lambda_L", rust)
        self.assertIn("command(__glyph_lambda", rust)
        self.assertIn("validate(i)?", rust)

    def test_single_line_slash_pipe(self) -> None:
        source = """
>inc(x:U):U=x+1
>double(x:U):U=x*2
>run(x:U):U=x /> inc /> |n| n+1 /> double
"""
        rust = compile_source(source)
        self.assertIn("double(__glyph_lambda", rust)
        self.assertIn("inc(x)", rust)

    def test_pipeline_lambda_cannot_capture_outer_parameter(self) -> None:
        source = """
>run(x:U,limit:U):U=x /> |n| min(n,limit)
"""
        with self.assertRaisesRegex(GlyphError, "捕捉"):
            compile_source(source)

    def test_pipeline_question_requires_result(self) -> None:
        source = """
>inc(x:U):U=x+1
>run(x:U):U=x /> inc?
"""
        with self.assertRaisesRegex(GlyphError, "Result"):
            compile_source(source)

    def test_visual_continuations_preserve_line_count(self) -> None:
        source = ">run(x:U):U=\n  x\n  /> |n| n+1\n\n>id(x:U):U=x\n"
        joined = join_pipeline_continuations(source)
        self.assertEqual(len(source.splitlines()), len(joined.splitlines()))
        self.assertIn(">run(x:U):U=x /> |n| n+1", joined)

    def test_system_builds_architecture_ir_and_mermaid(self) -> None:
        source = """
system Door
  sensor -> ctl
  panel -> ctl
  ctl -> lock
  ctl -> log

>ctl(x:U):U=x
!lock(x:U):B=true
!log(x:U):B=true
"""
        model = parse_compilation_model(source, "door.glyph")
        self.assertEqual(len(model.architecture.systems), 1)
        system = model.architecture.systems[0]
        kinds = {component.name: component.kind for component in system.components}
        self.assertEqual(kinds["sensor"], "external")
        self.assertEqual(kinds["ctl"], "function")
        self.assertEqual(kinds["lock"], "effect")
        bundle = compile_diagram_bundle(source, "door.glyph")
        self.assertIn("architecture.mmd", bundle.files)
        self.assertIn("architecture-ir.json", bundle.files)
        self.assertIn("sensor", bundle.files["architecture.mmd"])
        self.assertIn("ctl", bundle.files["architecture.mmd"])

    def test_duplicate_system_edge_is_rejected(self) -> None:
        source = """
system Broken
  a -> b
  a -> b
"""
        with self.assertRaisesRegex(GlyphError, "重複"):
            parse_compilation_model(source)

    def test_studio_has_architecture_logic_and_time_views(self) -> None:
        for label in ("Architecture", "State", "Logic", "Time"):
            self.assertIn(label, STUDIO_HTML)


if __name__ == "__main__":
    unittest.main()

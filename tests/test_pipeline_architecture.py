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
        source = ">run(x:U,limit:U):U=x /> |n| min(n,limit)\n"
        with self.assertRaisesRegex(GlyphError, "捕捉"):
            compile_source(source)

    def test_pipeline_question_requires_result(self) -> None:
        source = ">inc(x:U):U=x+1\n>run(x:U):U=x /> inc?\n"
        with self.assertRaisesRegex(GlyphError, "Result"):
            compile_source(source)

    def test_visual_continuations_preserve_line_count(self) -> None:
        source = ">run(x:U):U=\n  x\n  /> |n| n+1\n\n>id(x:U):U=x\n"
        joined = join_pipeline_continuations(source)
        self.assertEqual(len(source.splitlines()), len(joined.splitlines()))
        self.assertIn(">run(x:U):U=x /> |n| n+1", joined)

    def test_system_context_uses_boundary_flow_and_explicit_ext(self) -> None:
        source = """
system Door
  entry control
  in sensor:U
  in panel:U
  out result:B
  sensor -> control
  panel -> control
  control -> result
  control -> lock
  control -> log

ext sensor():U
ext panel():U
!lock(x:U):U
!log(x:U):B

>sum_inputs():U=sensor()+panel()
>control():B=log(lock(sum_inputs()))
"""
        model = parse_compilation_model(source, "door.glyph")
        system = model.architecture.systems[0]
        kinds = {component.name: component.kind for component in system.components}
        self.assertEqual(kinds["sensor"], "external")
        self.assertEqual(kinds["panel"], "external")
        self.assertEqual(kinds["control"], "function")
        self.assertEqual(kinds["lock"], "effect")
        self.assertEqual(kinds["log"], "effect")
        self.assertNotIn("sum_inputs", kinds)

        names = {component.id: component.name for component in system.components}
        edges = {(names[e.source_id], names[e.target_id], e.kind) for e in system.edges}
        self.assertEqual(
            edges,
            {
                ("sensor", "control", "data"),
                ("panel", "control", "data"),
                ("control", "result", "return"),
                ("control", "lock", "effect"),
                ("control", "log", "effect"),
            },
        )
        evidence_kinds = {item.kind for item in system.evidence}
        self.assertIn("external-input-read", evidence_kinds)
        self.assertIn("return-type", evidence_kinds)
        self.assertIn("effect-reachability", evidence_kinds)

        bundle = compile_diagram_bundle(source, "door.glyph")
        self.assertIn("architecture.mmd", bundle.files)
        self.assertIn("architecture-ir.json", bundle.files)
        self.assertIn("sensor", bundle.files["architecture.mmd"])
        self.assertIn("control", bundle.files["architecture.mmd"])

    def test_system_edges_are_checked_architecture_assertions(self) -> None:
        source = """
system Door
  entry control
  in x:U
  out result:()
  x -> control
  control -> result
  control -> actuator

!actuator(x:U):()
>control(x:U):()=actuator(x)
"""
        model = parse_compilation_model(source, "door.glyph")
        self.assertEqual(len(model.architecture.systems[0].edges), 3)

    def test_removed_equals_entry_syntax_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "system Name=entry.*廃止"):
            parse_compilation_model("system Broken=control\n>control(x:U):U=x\n")

    def test_undeclared_system_entry_is_rejected(self) -> None:
        source = """
system Broken
  entry missing
  in x:U
  out result:U
  x -> missing
  missing -> result
>present(x:U):U=x
"""
        with self.assertRaisesRegex(GlyphError, "entry 'missing' は未宣言"):
            parse_compilation_model(source)

    def test_undeclared_reachable_call_requires_ext(self) -> None:
        source = """
system Broken
  entry control
  in x:U
  out result:U
  x -> control
  control -> result
>control(x:U):U=driver(x)
"""
        with self.assertRaisesRegex(GlyphError, "ext name\\(args\\):Type"):
            parse_compilation_model(source)

    def test_undeclared_system_endpoint_is_rejected(self) -> None:
        source = """
system Broken
  entry control
  in x:U
  out result:U
  x -> control
  ghost -> control
  control -> result
>control(x:U):U=x
"""
        with self.assertRaisesRegex(GlyphError, "endpoint 'ghost' は未宣言"):
            parse_compilation_model(source)

    def test_asserted_effect_edge_must_exist_in_code(self) -> None:
        source = """
system Broken
  entry control
  in x:U
  out result:U
  x -> control
  control -> result
  control -> alarm
!alarm(x:U):()
>control(x:U):U=x
"""
        with self.assertRaisesRegex(GlyphError, "到達可能なコードpathが存在しない"):
            parse_compilation_model(source)

    def test_duplicate_system_assertion_is_rejected(self) -> None:
        source = """
system Broken
  entry control
  in x:U
  out result:()
  x -> control
  control -> result
  control -> alarm
  control -> alarm
!alarm(x:U):()
>control(x:U):()=alarm(x)
"""
        with self.assertRaisesRegex(GlyphError, "重複"):
            parse_compilation_model(source)

    def test_bare_system_requires_explicit_entry_ports_and_flow(self) -> None:
        with self.assertRaisesRegex(GlyphError, "entry function_name"):
            parse_compilation_model("system Empty\n>entry(x:U):U=x\n")

    def test_studio_has_architecture_logic_and_time_views(self) -> None:
        for label in ("Architecture", "State", "Logic", "Time"):
            self.assertIn(label, STUDIO_HTML)


if __name__ == "__main__":
    unittest.main()

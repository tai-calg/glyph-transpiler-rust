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

    def test_system_context_uses_entry_source_sink_and_derived_calls(self) -> None:
        source = """
system Door
  entry control
  source sensor
  source panel
  sink lock
  sink log

ext sensor():U
ext panel():U
!lock(x:U):U
!log(x:U):B

>sum_inputs():U=sensor()+panel()
>control():B=log(lock(sum_inputs()))
"""
        model = parse_compilation_model(source, "door.glyph")
        declaration = model.systems[0]
        self.assertEqual(declaration.entry_name, "control")
        self.assertEqual(declaration.source_names, ("sensor", "panel"))
        self.assertEqual(declaration.sink_names, ("lock", "log"))

        system = model.architecture.systems[0]
        self.assertEqual(system.entry, "control")
        self.assertEqual(system.sources, ("sensor", "panel"))
        self.assertEqual(system.sinks, ("log", "lock"))
        self.assertEqual(system.ports, ())

        components = {component.name: component for component in system.components}
        self.assertEqual(components["control"].role, "entry")
        self.assertEqual(components["sum_inputs"].role, "internal")
        self.assertEqual(components["sensor"].role, "source")
        self.assertEqual(components["panel"].role, "source")
        self.assertEqual(components["lock"].role, "sink")
        self.assertEqual(components["log"].role, "sink")

        names = {component.id: component.name for component in system.components}
        edges = {(names[e.source_id], names[e.target_id], e.kind) for e in system.edges}
        self.assertEqual(
            edges,
            {
                ("control", "log", "call"),
                ("control", "lock", "call"),
                ("control", "sum_inputs", "call"),
                ("sum_inputs", "sensor", "call"),
                ("sum_inputs", "panel", "call"),
            },
        )
        self.assertEqual({item.kind for item in system.evidence}, {"call"})

        bundle = compile_diagram_bundle(source, "door.glyph")
        self.assertIn("architecture.mmd", bundle.files)
        self.assertIn("architecture-ir.json", bundle.files)
        self.assertIn("sum_inputs", bundle.files["architecture.mmd"])
        self.assertIn("control", bundle.files["architecture.mmd"])

    def test_entry_signature_is_the_complete_system_request_and_response(self) -> None:
        source = """
system Door
  entry control
  source sensor
  sink actuator

+Error=ReadFailed|WriteFailed
*Input(open:B)
*Receipt(done:B)
ext sensor():Input|Error
!actuator(input:Input):Receipt|Error
>control():Receipt|Error=actuator(sensor()?)
"""
        model = parse_compilation_model(source, "door.glyph")
        system = model.architecture.systems[0]
        self.assertEqual(system.entry, "control")
        self.assertEqual(system.sources, ("sensor",))
        self.assertEqual(system.sinks, ("actuator",))
        self.assertEqual(system.ports, ())

    def test_missing_reachable_source_is_rejected(self) -> None:
        source = """
system Broken
  entry control
ext sensor():U
>control():U=sensor()
"""
        with self.assertRaisesRegex(GlyphError, "sourceとして宣言していない"):
            parse_compilation_model(source)

    def test_missing_reachable_sink_is_rejected(self) -> None:
        source = """
system Broken
  entry control
!actuator(x:U):()
>control(x:U):()=actuator(x)
"""
        with self.assertRaisesRegex(GlyphError, "sinkとして宣言していない"):
            parse_compilation_model(source)

    def test_source_must_be_ext_function(self) -> None:
        source = """
system Broken
  entry control
  source helper
>helper():U=1
>control():U=helper()
"""
        with self.assertRaisesRegex(GlyphError, "`ext`外部入力関数"):
            parse_compilation_model(source)

    def test_sink_must_be_effect_function(self) -> None:
        source = """
system Broken
  entry control
  sink helper
>helper(x:U):U=x
>control(x:U):U=helper(x)
"""
        with self.assertRaisesRegex(GlyphError, "`!`外部作用関数"):
            parse_compilation_model(source)

    def test_declared_boundary_must_be_reachable_from_entry(self) -> None:
        source = """
system Broken
  entry control
  source sensor
ext sensor():U
>control():U=1
"""
        with self.assertRaisesRegex(GlyphError, "entry 'control' から呼び出されない"):
            parse_compilation_model(source)

    def test_duplicate_boundary_role_is_rejected(self) -> None:
        source = """
system Broken
  entry control
  source sensor
  sink sensor
ext sensor():U
>control():U=sensor()
"""
        with self.assertRaisesRegex(GlyphError, "sourceとして宣言済み"):
            parse_compilation_model(source)

    def test_pure_system_needs_only_entry(self) -> None:
        source = """
system Pure
  entry control
>helper(x:U):U=x+1
>control(x:U):U=helper(x)
"""
        model = parse_compilation_model(source)
        system = model.architecture.systems[0]
        self.assertEqual(system.sources, ())
        self.assertEqual(system.sinks, ())
        self.assertEqual(
            {component.name for component in system.components},
            {"control", "helper"},
        )

    def test_legacy_system_flow_is_accepted_but_not_authoritative(self) -> None:
        source = """
system Legacy
  entry control
  in x:U
  out result:()
  x -> control
  control -> result
  control -> actuator
!actuator(x:U):()
>control(x:U):()=actuator(x)
"""
        model = parse_compilation_model(source)
        declaration = model.systems[0]
        self.assertEqual(declaration.syntax, "legacy-flow")
        system = model.architecture.systems[0]
        self.assertEqual(system.ports, ())
        self.assertEqual(system.sinks, ("actuator",))
        self.assertEqual(len(system.edges), 1)
        self.assertEqual(system.edges[0].kind, "call")

    def test_removed_equals_entry_syntax_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "system Name=entry.*廃止"):
            parse_compilation_model("system Broken=control\n>control(x:U):U=x\n")

    def test_undeclared_system_entry_is_rejected(self) -> None:
        source = """
system Broken
  entry missing
>present(x:U):U=x
"""
        with self.assertRaisesRegex(GlyphError, "entry 'missing' は未宣言"):
            parse_compilation_model(source)

    def test_undeclared_reachable_call_requires_ext(self) -> None:
        source = """
system Broken
  entry control
>control(x:U):U=driver(x)
"""
        with self.assertRaisesRegex(GlyphError, "ext name\\(args\\):Type"):
            parse_compilation_model(source)

    def test_bare_system_requires_explicit_entry(self) -> None:
        with self.assertRaisesRegex(GlyphError, "entry function_name"):
            parse_compilation_model("system Empty\n>entry(x:U):U=x\n")

    def test_studio_has_architecture_logic_and_time_views(self) -> None:
        for label in ("Architecture", "State", "Logic", "Time"):
            self.assertIn(label, STUDIO_HTML)


if __name__ == "__main__":
    unittest.main()

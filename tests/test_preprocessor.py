from __future__ import annotations

import json
import unittest

from glyph import GlyphError, compile_diagram_bundle, compile_source, parse_compilation_model
from glyph.preprocessor import preprocess_source


class RawPreprocessorTests(unittest.TestCase):
    def test_raw_macro_expands_across_declarations_types_and_expressions(self) -> None:
        source = """
@TYPE=SensorInput
@DECL=*TYPE(value:U)
@LIMIT=100
DECL
>cap(x:U):U
  x>LIMIT >> LIMIT
  _ >> x
>wrap(x:U):TYPE=TYPE(x)
"""
        rust = compile_source(source)
        self.assertIn("pub struct SensorInput", rust)
        self.assertIn("if x > 100", rust)
        self.assertIn("SensorInput { value: x }", rust)

    def test_raw_macro_expands_system_edges(self) -> None:
        source = """
@EDGE=sensor -> ctl
system Demo
  EDGE
!sensor():U
>ctl(x:U):U=x
"""
        model = parse_compilation_model(source)
        edge = model.systems[0].edges[0]
        self.assertEqual((edge.source_name, edge.target_name), ("sensor", "ctl"))
        self.assertEqual(edge.line, 4)

    def test_multiline_macro_expands_immutable_algorithm_block(self) -> None:
        source = """@MAX=100
@NORMALIZE
  positive :=
    x<0 >> -x
    _ >> x

  limited :=
    positive>MAX >> MAX
    _ >> positive
@end
>process(x:I):I
  NORMALIZE
  limited
"""
        rust = compile_source(source)
        self.assertIn("let positive", rust)
        self.assertIn("let limited", rust)
        self.assertIn("positive > 100", rust)

        model = parse_compilation_model(source)
        self.assertEqual([item.name for item in model.blocks[0].bindings], ["positive", "limited"])
        self.assertEqual([item.line for item in model.blocks[0].bindings], [12, 12])

    def test_multiline_macro_must_be_used_as_a_whole_line(self) -> None:
        source = """
@BLOCK
  *Point(x:I)
@end
BLOCK BLOCK
"""
        with self.assertRaisesRegex(GlyphError, "行に単独"):
            compile_source(source)

    def test_raw_macro_names_are_uppercase_only(self) -> None:
        with self.assertRaisesRegex(GlyphError, "大文字"):
            compile_source("@limit=10\n>f():I=1\n")

    def test_lowercase_function_like_ast_macro_remains_supported(self) -> None:
        source = """
@MAX=10
@limit(x)=min(x,MAX)
>f(x:U):U=limit(x)
"""
        rust = compile_source(source)
        self.assertIn("std::cmp::min(x, 10)", rust)
        model = parse_compilation_model(source)
        self.assertEqual(model.ast_macros[0].name, "limit")

    def test_nested_raw_macros_are_resolved_without_substring_replacement(self) -> None:
        result = preprocess_source(
            "@BASE=10\n@LIMIT=BASE+5\n@IN=Value\n*Input(IN:I)\n>f():I=LIMIT\n"
        )
        self.assertIn("*Input(Value:I)", result.source)
        self.assertIn(">f():I=10+5", result.source)
        self.assertNotIn("*Valueput", result.source)

    def test_comments_are_not_macro_expanded(self) -> None:
        result = preprocess_source("@MAX=10\n>f():I=MAX # MAX remains documentation\n")
        self.assertIn(">f():I=10 # MAX remains documentation", result.source)

    def test_raw_macro_cycle_is_rejected_even_when_unused(self) -> None:
        with self.assertRaisesRegex(GlyphError, "raw macro cycle: A -> B -> A"):
            compile_source("@A=B\n@B=A\n>f():I=1\n")

    def test_expanded_diagnostic_is_mapped_to_invocation_line(self) -> None:
        source = """@BAD
  not_a_declaration
@end

BAD
"""
        with self.assertRaisesRegex(GlyphError, "5行目"):
            compile_source(source)

    def test_preprocessed_source_and_mapping_are_artifacts(self) -> None:
        source = "@TYPE=Point\n*TYPE(x:I)\n"
        bundle = compile_diagram_bundle(source, "macro.glyph")
        self.assertEqual(bundle.files["preprocessed.glyph"], "*Point(x:I)\n")
        mapping = json.loads(bundle.files["preprocessor-map.json"])
        self.assertEqual(mapping["schema"], "glyph.preprocessor-map")
        self.assertEqual(mapping["version"], 1)
        self.assertEqual(mapping["macros"][0]["name"], "TYPE")
        self.assertEqual(mapping["expanded_lines"][0]["source_line"], 2)
        self.assertEqual(mapping["expanded_lines"][0]["macro_stack"], ["TYPE"])

    def test_raw_substitution_is_intentionally_textual_not_parenthesized(self) -> None:
        rust = compile_source("@NEXT=x+1\n>f(x:I):I=NEXT*2\n")
        self.assertIn("x + 1 * 2", rust)
        self.assertNotIn("(x + 1) * 2", rust)


if __name__ == "__main__":
    unittest.main()

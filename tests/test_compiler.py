from __future__ import annotations

import unittest
from pathlib import Path

from glyph import GlyphError, compile_artifacts, compile_source, parse_program


ROOT = Path(__file__).resolve().parents[1]


class CompilerTests(unittest.TestCase):
    def test_controller_example_generates_expected_rust(self) -> None:
        source = (ROOT / "examples" / "controller.glyph").read_text(encoding="utf-8")
        artifacts = compile_artifacts(source)

        self.assertIn("pub struct S", artifacts.logic)
        self.assertIn("pub enum C", artifacts.logic)
        self.assertIn("C::Run(std::cmp::min(s.r, 1000))", artifacts.logic)
        self.assertIn("crate::host::exec(cmd(decode(v, t, r)?))", artifacts.logic)
        self.assertIn("if !v.is_finite() || !t.is_finite() || v < 0.0", artifacts.logic)
        self.assertIn("pub fn exec(c: C) -> Result<Receipt, E>", artifacts.host)
        self.assertIn("Ok(Receipt { c: c })", artifacts.host)

    def test_generation_is_deterministic(self) -> None:
        source = (ROOT / "examples" / "controller.glyph").read_text(encoding="utf-8")
        self.assertEqual(compile_artifacts(source), compile_artifacts(source))

    def test_product_constructor_uses_declared_field_order(self) -> None:
        generated = compile_source("*P(x:i32,y:i32)\n>mk(x:i32,y:i32):P=P(x,y)\n")
        self.assertIn("P { x: x, y: y }", generated)

    def test_sum_variants_are_namespaced(self) -> None:
        generated = compile_source("+State=Idle|Run(u16)\n>f():State=Run(3)\n")
        self.assertIn("State::Run(3)", generated)

    def test_type_shorthands(self) -> None:
        generated = compile_source("+E=Bad\n=x=R<u16,E>\n")
        self.assertIn("pub type x = Result<u16, E>;", generated)

    def test_compact_grouped_fields_result_spread_and_guard_arrow(self) -> None:
        generated = compile_source(
            "*S(v,t:F,r:U)\n"
            "+E=Bad\n"
            ">decode(*S):S|E\n"
            "  v<0>>Err(Bad)\n"
            "  _>>Ok(S(v,t,r))\n"
        )
        self.assertIn("pub v: f32", generated)
        self.assertIn("pub t: f32", generated)
        self.assertIn("pub r: u16", generated)
        self.assertIn(
            "pub fn decode(v: f32, t: f32, r: u16) -> Result<S, E>",
            generated,
        )
        self.assertIn("else {\n        Ok(S { v: v, t: t, r: r })", generated)

    def test_question_mark_is_reserved_for_failure_propagation(self) -> None:
        with self.assertRaises(GlyphError):
            compile_source("+E=Bad\n>f():U?E=Err(Bad)\n")

    def test_slash_is_not_a_compact_result_type(self) -> None:
        with self.assertRaises(GlyphError):
            compile_source("+E=Bad\n>f():U/E=Err(Bad)\n")

    def test_compact_primitive_type_shortcuts(self) -> None:
        generated = compile_source("*P(x:F,y:D,n:U,k:I,ok:B)\n")
        self.assertIn("pub x: f32", generated)
        self.assertIn("pub y: f64", generated)
        self.assertIn("pub n: u16", generated)
        self.assertIn("pub k: i32", generated)
        self.assertIn("pub ok: bool", generated)

    def test_legacy_lowercase_type_shortcuts_are_rejected(self) -> None:
        for old, new in (("f", "F"), ("d", "D"), ("u", "U"), ("i", "I"), ("b", "B")):
            with self.subTest(old=old):
                with self.assertRaisesRegex(GlyphError, f"'{new}'"):
                    compile_source(f"*P(value:{old})\n")

    def test_declared_type_name_overrides_primitive_shortcut(self) -> None:
        generated = compile_source("*F(x:I)\n>id(x:F):F=x\n")
        self.assertIn("pub struct F", generated)
        self.assertIn("pub fn id(x: F) -> F", generated)

    def test_unknown_product_spread_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "積型 '\\*Missing' が定義されていない"):
            compile_source(">f(*Missing):I=0\n")

    def test_guard_function_requires_explicit_final_fallback(self) -> None:
        with self.assertRaises(GlyphError):
            parse_program(">f(x:I):I\n  x<0>>0\n  1\n")

    def test_guard_function_requires_final_fallback(self) -> None:
        with self.assertRaisesRegex(GlyphError, "最後にちょうど1個"):
            parse_program(">f(x:i32):i32\n  x<0>>0\n")

    def test_legacy_guard_arrow_remains_compatible(self) -> None:
        generated = compile_source(">f(x:I):I\n  x<0=>0\n  _=>1\n")
        self.assertIn("if x < 0", generated)

    def test_single_equal_is_rejected_in_guard_expression(self) -> None:
        with self.assertRaisesRegex(GlyphError, "'=='"):
            compile_source(">same(x,y:I):B\n  x=y>>true\n  _>>false\n")

    def test_double_equal_is_boolean_comparison(self) -> None:
        generated = compile_source(">same(x,y:I):B\n  x==y>>true\n  _>>false\n")
        self.assertIn("if x == y", generated)

    def test_single_equal_is_rejected_after_raw_macro_expansion(self) -> None:
        with self.assertRaisesRegex(GlyphError, "'=='"):
            compile_source("@ZERO=x=0\n>f(x:I):B=ZERO\n")

    def test_duplicate_variant_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "衝突"):
            parse_program("+A=X\n+B=X\n")

    def test_wrong_constructor_arity_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "2引数"):
            compile_source("*P(x:i32,y:i32)\n>mk():P=P(1)\n")

    def test_external_effect_is_routed_to_host_module(self) -> None:
        artifacts = compile_artifacts(
            "!send(x:u8):R<u8,u8>\n>run(x:u8):R<u8,u8>=send(x)\n"
        )
        self.assertIn("crate::host::send(x)", artifacts.logic)
        self.assertIn("panic!(\"Glyph effect boundary `send` is not connected\")", artifacts.host)

    def test_inline_effect_generates_prototype_host_implementation(self) -> None:
        artifacts = compile_artifacts(
            "*Receipt(x:u8)\n!send(x:u8):Receipt|u8=Ok(Receipt(x))\n"
        )
        self.assertNotIn("pub fn send", artifacts.logic)
        self.assertIn("pub fn send(x: u8) -> Result<Receipt, u8>", artifacts.host)
        self.assertIn("Ok(Receipt { x: x })", artifacts.host)

    def test_word_macro_expands_only_complete_identifier_tokens(self) -> None:
        generated = compile_source("@M=1000\n>cap(requested:u16):u16=min(requested,M)\n")
        self.assertIn("std::cmp::min(requested, 1000)", generated)

    def test_raw_macro_is_textual_and_does_not_add_parentheses(self) -> None:
        generated = compile_source("@NEXT=x+1\n>double_next(x:i32):i32=NEXT*2\n")
        self.assertIn("x + 1 * 2", generated)
        self.assertNotIn("(x + 1) * 2", generated)

    def test_macro_can_alias_a_function_name(self) -> None:
        generated = compile_source("@LOWER=min\n>f(x:u16):u16=LOWER(x,10)\n")
        self.assertIn("std::cmp::min(x, 10)", generated)

    def test_nested_macros_are_resolved(self) -> None:
        generated = compile_source("@BASE=10\n@LIMIT=BASE+5\n>f():i32=LIMIT\n")
        self.assertIn("10 + 5", generated)

    def test_macro_does_not_replace_substrings_inside_identifiers(self) -> None:
        generated = compile_source("@R=1\n>f(Receipt:i32):i32=Receipt\n")
        self.assertIn("pub fn f(Receipt: i32) -> i32", generated)
        self.assertIn("    Receipt", generated)

    def test_duplicate_macro_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "既に定義済み"):
            parse_program("@A=1\n@A=2\n>f():i32=A\n")

    def test_macro_cycle_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "raw macro cycle: A -> B -> A"):
            parse_program("@A=B\n@B=A\n>f():i32=A\n")

    def test_unused_raw_macro_body_may_be_arbitrary_source_text(self) -> None:
        generated = compile_source("@ARBITRARY=1+\n>f():i32=1\n")
        self.assertIn("pub fn f() -> i32", generated)

    def test_object_like_raw_macro_name_must_be_uppercase(self) -> None:
        with self.assertRaisesRegex(GlyphError, "大文字"):
            parse_program("@run=1\n>run():i32=1\n")


if __name__ == "__main__":
    unittest.main()

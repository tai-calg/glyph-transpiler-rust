from __future__ import annotations

import unittest
from pathlib import Path

from glyph.compiler import GlyphError, compile_source, parse_program


ROOT = Path(__file__).resolve().parents[1]


class CompilerTests(unittest.TestCase):
    def test_controller_example_generates_expected_rust(self) -> None:
        source = (ROOT / "examples" / "controller.glyph").read_text(encoding="utf-8")
        generated = compile_source(source)

        self.assertIn("pub struct S", generated)
        self.assertIn("pub enum C", generated)
        self.assertIn("C::Run(std::cmp::min(s.r, 1000))", generated)
        self.assertIn("crate::host::exec(cmd(decode(v, t, r)?))", generated)
        self.assertIn("if !v.is_finite() || !t.is_finite() || v < 0", generated)

    def test_generation_is_deterministic(self) -> None:
        source = (ROOT / "examples" / "controller.glyph").read_text(encoding="utf-8")
        self.assertEqual(compile_source(source), compile_source(source))

    def test_product_constructor_uses_declared_field_order(self) -> None:
        generated = compile_source("*P(x:i32,y:i32)\n>mk(x:i32,y:i32):P=P(x,y)\n")
        self.assertIn("P { x: x, y: y }", generated)

    def test_sum_variants_are_namespaced(self) -> None:
        generated = compile_source("+State=Idle|Run(u16)\n>f():State=Run(3)\n")
        self.assertIn("State::Run(3)", generated)

    def test_type_shorthands(self) -> None:
        generated = compile_source("+E=Bad\n=x=R<u16,E>\n")
        self.assertIn("pub type x = Result<u16, E>;", generated)

    def test_guard_function_requires_final_fallback(self) -> None:
        with self.assertRaisesRegex(GlyphError, "最後にちょうど1個"):
            parse_program(">f(x:i32):i32\n  x<0 => 0\n")

    def test_duplicate_variant_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "衝突"):
            parse_program("+A=X\n+B=X\n")

    def test_wrong_constructor_arity_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "2引数"):
            compile_source("*P(x:i32,y:i32)\n>mk():P=P(1)\n")

    def test_external_effect_is_routed_to_host_module(self) -> None:
        generated = compile_source("!send(x:u8):R<u8,u8>\n>run(x:u8):R<u8,u8>=send(x)\n")
        self.assertIn("crate::host::send(x)", generated)

    def test_word_macro_expands_only_complete_identifier_tokens(self) -> None:
        generated = compile_source("@M=1000\n>cap(requested:u16):u16=min(requested,M)\n")
        self.assertIn("std::cmp::min(requested, 1000)", generated)

    def test_expression_macro_is_parenthesized_to_preserve_precedence(self) -> None:
        generated = compile_source("@NEXT=x+1\n>double_next(x:i32):i32=NEXT*2\n")
        self.assertIn("(x + 1) * 2", generated)

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
        with self.assertRaisesRegex(GlyphError, "macro cycle: A -> B -> A"):
            parse_program("@A=B\n@B=A\n>f():i32=A\n")

    def test_invalid_unused_macro_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "マクロ 'BAD'"):
            parse_program("@BAD=1+\n>f():i32=1\n")

    def test_macro_name_cannot_shadow_a_declared_symbol(self) -> None:
        with self.assertRaisesRegex(GlyphError, "宣言またはvariant名と衝突"):
            parse_program("@run=1\n>run():i32=1\n")


if __name__ == "__main__":
    unittest.main()

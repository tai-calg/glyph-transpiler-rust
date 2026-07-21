from __future__ import annotations

import unittest

from glyph import GlyphError, compile_source, parse_program
from glyph.temporal import Always, Implies, Until, Within, parse_formula
from glyph.temporal_sigils import normalize_temporal_sigils
from glyph.syntax import expand_compact_syntax


class TemporalTests(unittest.TestCase):
    def test_ascii_response_formula_parses(self) -> None:
        source = normalize_temporal_sigils(
            "?ack(send,ack:B)=@A(send>>@E 5s ack)\n"
        )
        expanded = expand_compact_syntax(source)
        formula_text = expanded.split("=", 1)[1].strip()
        formula = parse_formula(formula_text)
        self.assertIsInstance(formula, Always)
        self.assertIsInstance(formula.value, Implies)
        self.assertIsInstance(formula.value.consequence, Within)
        self.assertEqual(formula.value.consequence.milliseconds, 5000)

    def test_until_and_weak_until_are_distinct(self) -> None:
        strong = parse_formula("closed U auth")
        weak = parse_formula("closed W auth")
        self.assertIsInstance(strong, Until)
        self.assertIsInstance(weak, Until)
        self.assertFalse(strong.weak)
        self.assertTrue(weak.weak)

    def test_operator_chain_requires_operand_boundary(self) -> None:
        generated = compile_source("?conv(EAstable:B)=@E@A stable\n")
        self.assertIn("pub struct ConvMonitor", generated)

    def test_temporal_spec_generates_monitor(self) -> None:
        generated = compile_source(
            "*O(send,ack:B)\n"
            "?ack(*O)=@A(send>>@E 5s ack)\n"
        )
        self.assertIn("pub enum TemporalVerdict", generated)
        self.assertIn("pub struct AckMonitor", generated)
        self.assertIn("saturating_add(5000)", generated)
        self.assertIn("pub fn step(&mut self, at_ms: u64, send: bool, ack: bool)", generated)

    def test_specs_are_removed_before_core_program_parse(self) -> None:
        program = parse_program(
            "*O(send,ack:B)\n"
            "?ack(*O)=@A(send>>@E 5s ack)\n"
        )
        self.assertEqual(len(program.declarations), 1)

    def test_bare_temporal_operator_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "裸の時相演算子 'A'"):
            compile_source("?x(done:B)=A done\n")
        with self.assertRaisesRegex(GlyphError, "'@A@E'"):
            compile_source("?x(done:B)=AE 1s done\n")

    def test_unicode_temporal_operators_are_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "'@A' と '@E'"):
            compile_source("?x(done:B)=◇done\n")

    def test_reserved_temporal_macro_names_are_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "時相演算子 '@A'.*予約済み"):
            compile_source("@A=other\n?x(done:B)=@A done\n")
        with self.assertRaisesRegex(GlyphError, "時相演算子 '@E'.*予約済み"):
            compile_source("@E\n  value\n@end\n?x(done:B)=@E done\n")

    def test_zero_duration_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "0より大きく"):
            compile_source("?deadline(done:B)=@E 0s done\n")

    def test_unknown_product_spread_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "積型 '\\*Missing' が定義されていない"):
            compile_source("?x(*Missing)=@A true\n")

    def test_duplicate_spec_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "既に定義済み"):
            compile_source("?x(p:B)=@A p\n?x(p:B)=@E p\n")

    def test_single_equal_is_rejected_inside_temporal_atom(self) -> None:
        with self.assertRaisesRegex(GlyphError, "'=='"):
            compile_source("?same(x,y:I)=@A(x=y)\n")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from glyph import GlyphError, compile_source, parse_program
from glyph.temporal import Always, Implies, Until, Within, parse_formula


class TemporalTests(unittest.TestCase):
    def test_compact_response_formula_parses(self) -> None:
        formula = parse_formula("□(send>>◇5s ack)")
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

    def test_temporal_spec_generates_monitor(self) -> None:
        generated = compile_source(
            "*O(send,ack:b)\n"
            "?ack(*O)=□(send>>◇5s ack)\n"
        )
        self.assertIn("pub enum TemporalVerdict", generated)
        self.assertIn("pub struct AckMonitor", generated)
        self.assertIn("saturating_add(5000)", generated)
        self.assertIn("pub fn step(&mut self, at_ms: u64, send: bool, ack: bool)", generated)

    def test_specs_are_removed_before_core_program_parse(self) -> None:
        program = parse_program(
            "*O(send,ack:b)\n"
            "?ack(*O)=□(send>>◇5s ack)\n"
        )
        self.assertEqual(len(program.declarations), 1)

    def test_zero_duration_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "0より大きく"):
            compile_source("?deadline(done:b)=◇0s done\n")

    def test_unknown_product_spread_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "積型 '\\*Missing' が定義されていない"):
            compile_source("?x(*Missing)=□true\n")

    def test_duplicate_spec_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "既に定義済み"):
            compile_source("?x(p:b)=□p\n?x(p:b)=◇p\n")


if __name__ == "__main__":
    unittest.main()

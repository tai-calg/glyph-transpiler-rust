from __future__ import annotations

import unittest

from glyph import GlyphError, compile_source
from glyph.temporal import Implies, parse_formula


class TemporalSemanticTests(unittest.TestCase):
    def test_implication_is_right_associative(self) -> None:
        formula = parse_formula("a>>b>>c")
        self.assertIsInstance(formula, Implies)
        self.assertIsInstance(formula.consequence, Implies)

    def test_pure_helper_function_is_allowed_in_atom(self) -> None:
        generated = compile_source(
            ">valid(p:b):b=p\n"
            "?x(p:b)=□valid(p)\n"
        )
        self.assertIn("pub struct XMonitor", generated)

    def test_direct_effect_call_is_rejected_in_atom(self) -> None:
        with self.assertRaisesRegex(GlyphError, "外部作用"):
            compile_source(
                "!read():b\n"
                "?x(p:b)=□read()\n"
            )

    def test_transitive_effect_call_is_rejected_in_atom(self) -> None:
        with self.assertRaisesRegex(GlyphError, "外部作用"):
            compile_source(
                "!read():b\n"
                ">probe():b=read()\n"
                "?x(p:b)=□probe()\n"
            )

    def test_unknown_call_is_rejected_in_atom(self) -> None:
        with self.assertRaisesRegex(GlyphError, "純粋性を確認できない"):
            compile_source("?x(p:b)=□mystery(p)\n")

    def test_try_propagation_is_rejected_in_atom(self) -> None:
        with self.assertRaisesRegex(GlyphError, "失敗伝播"):
            compile_source("?x(p:b)=□p?\n")

    def test_dynamic_call_is_rejected_in_atom(self) -> None:
        with self.assertRaisesRegex(GlyphError, "動的な呼出し"):
            compile_source("*F(run:b)\n?x(f:F)=□f.run()\n")


if __name__ == "__main__":
    unittest.main()

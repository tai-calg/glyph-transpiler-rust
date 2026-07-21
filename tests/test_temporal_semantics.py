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
            ">valid(p:B):B=p\n"
            "?x(p:B)=@A valid(p)\n"
        )
        self.assertIn("pub struct XMonitor", generated)

    def test_direct_effect_call_is_rejected_in_atom(self) -> None:
        with self.assertRaisesRegex(GlyphError, "外部作用"):
            compile_source(
                "!read():B\n"
                "?x(p:B)=@A read()\n"
            )

    def test_transitive_effect_call_is_rejected_in_atom(self) -> None:
        with self.assertRaisesRegex(GlyphError, "外部作用"):
            compile_source(
                "!read():B\n"
                ">probe():B=read()\n"
                "?x(p:B)=@A probe()\n"
            )

    def test_unknown_call_is_rejected_in_atom(self) -> None:
        with self.assertRaisesRegex(GlyphError, "純粋性を確認できない"):
            compile_source("?x(p:B)=@A mystery(p)\n")

    def test_try_propagation_is_rejected_in_atom(self) -> None:
        with self.assertRaisesRegex(GlyphError, "失敗伝播"):
            compile_source("?x(p:B)=@A p?\n")

    def test_dynamic_call_is_rejected_in_atom(self) -> None:
        with self.assertRaisesRegex(GlyphError, "動的な呼出し"):
            compile_source("*F(run:B)\n?x(f:F)=@A f.run()\n")


if __name__ == "__main__":
    unittest.main()

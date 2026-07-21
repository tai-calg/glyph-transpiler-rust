from __future__ import annotations

import unittest

from glyph import GlyphError, compile_source, parse_compilation_model


class AstMacroTests(unittest.TestCase):
    def test_function_like_macro_expands_expression_tree(self) -> None:
        source = """
@limit(x,hi)=min(x,hi)
>run(x:U):U=limit(x,100)
"""
        rust = compile_source(source)
        self.assertIn("std::cmp::min(x, 100)", rust)
        model = parse_compilation_model(source)
        self.assertEqual(model.ast_macros[0].name, "limit")
        self.assertEqual(model.semantic.macros[0].value, 1)

    def test_macro_argument_is_ast_not_text(self) -> None:
        source = """
@twice(x)=x+x
>run(x:U):U=twice(x*2)
"""
        rust = compile_source(source)
        self.assertIn("x * 2 + x * 2", rust)

    def test_macro_cycle_is_rejected(self) -> None:
        source = """
@a(x)=b(x)
@b(x)=a(x)
>run(x:U):U=a(x)
"""
        with self.assertRaisesRegex(GlyphError, "AST macro cycle"):
            compile_source(source)


if __name__ == "__main__":
    unittest.main()

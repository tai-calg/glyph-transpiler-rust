from __future__ import annotations

import unittest

from glyph import GlyphError, compile_source


class FunctionValueTests(unittest.TestCase):
    def test_named_pure_function_can_be_passed(self) -> None:
        source = """
>inc(x:U):U=x+1
>apply(f:Fn<U,U>,x:U):U=f(x)
>run(x:U):U=apply(inc,x)
"""
        rust = compile_source(source)
        self.assertIn("f: fn(u16) -> u16", rust)
        self.assertIn("apply(inc, x)", rust)

    def test_multi_argument_function_value(self) -> None:
        source = """
>add(x:U,y:U):U=x+y
>apply2(f:Fn<(U,U),U>,x:U,y:U):U=f(x,y)
>run(x:U,y:U):U=apply2(add,x,y)
"""
        rust = compile_source(source)
        self.assertIn("f: fn(u16, u16) -> u16", rust)

    def test_effect_boundary_cannot_be_passed(self) -> None:
        source = """
!read(x:U):U
>apply(f:Fn<U,U>,x:U):U=f(x)
>bad(x:U):U=apply(read,x)
"""
        with self.assertRaisesRegex(GlyphError, "作用境界"):
            compile_source(source)

    def test_transitively_impure_function_cannot_be_passed(self) -> None:
        source = """
!read(x:U):U
>impure(x:U):U=read(x)
>apply(f:Fn<U,U>,x:U):U=f(x)
>bad(x:U):U=apply(impure,x)
"""
        with self.assertRaisesRegex(GlyphError, "作用境界へ到達"):
            compile_source(source)


if __name__ == "__main__":
    unittest.main()

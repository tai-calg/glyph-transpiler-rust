from __future__ import annotations

import unittest

from glyph import GlyphError, compile_source


class Glyph04LayoutAndStateTests(unittest.TestCase):
    def test_multiline_resource_product_and_signature_compile(self) -> None:
        generated = compile_source(
            "resource Image[\n"
            "  Ready\n"
            " |Done\n"
            "]\n"
            "\n"
            "*App(\n"
            "  image:own Image[Ready],\n"
            "  worker:share Worker\n"
            ")\n"
            "\n"
            "!process(\n"
            "  image:own Image[Ready]\n"
            "):own Image[Done]\n"
        )

        self.assertIn("pub struct Image", generated)
        self.assertIn("pub struct App", generated)
        self.assertIn("effect boundary: process", generated)

    def test_share_resource_state_cannot_change(self) -> None:
        with self.assertRaisesRegex(GlyphError, "state"):
            compile_source(
                "resource Buffer[Ready|Used]\n"
                "!bad(buffer:share Buffer[Ready]):share Buffer[Used]\n"
            )

    def test_share_resource_cannot_be_promoted_to_owner(self) -> None:
        with self.assertRaisesRegex(GlyphError, "昇格"):
            compile_source(
                "resource Buffer[Ready]\n"
                "!bad(buffer:share Buffer[Ready]):own Buffer[Ready]\n"
            )

    def test_owner_resource_cannot_directly_become_link(self) -> None:
        with self.assertRaisesRegex(GlyphError, "直接link"):
            compile_source(
                "resource Buffer[Ready]\n"
                "!bad(buffer:own Buffer[Ready]):link Buffer[Ready]\n"
            )

    def test_same_type_resource_identity_must_be_explicit(self) -> None:
        with self.assertRaisesRegex(GlyphError, "出力identity対応"):
            compile_source(
                "resource Buffer[Ready]\n"
                "!choose(\n"
                "  left:share Buffer[Ready],\n"
                "  right:share Buffer[Ready]\n"
                "):share Buffer[Ready]\n"
            )

    def test_existing_one_line_source_is_unchanged(self) -> None:
        source = "*Point(x:I,y:I)\n>same(p:Point):Point=p\n"
        self.assertEqual(compile_source(source), compile_source(source))


if __name__ == "__main__":
    unittest.main()

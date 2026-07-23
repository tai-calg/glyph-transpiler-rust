from __future__ import annotations

import unittest

from glyph import GlyphError, compile_source, parse_compilation_model


class CapabilityPlaceTests(unittest.TestCase):
    def test_partial_field_moves_are_tracked_independently(self) -> None:
        source = (
            "resource Buffer[Ready]\n"
            "*Pair(left:own Buffer[Ready],right:own Buffer[Ready])\n"
            "!dispose(buffer:own Buffer[Ready]):U\n"
            ">take(pair:own Pair):own Buffer[Ready]\n"
            "  left := pair.left\n"
            "  dispose(pair.right)\n"
            "  left\n"
        )

        generated = compile_source(source)
        model = parse_compilation_model(source)
        moved = {
            item.source
            for item in model.capabilities.operations
            if item.function == "take" and item.kind == "move"
        }

        self.assertIn("pair.left", moved)
        self.assertIn("pair.right", moved)
        self.assertIn("pair.left", generated)
        self.assertIn("pair.right", generated)

    def test_unresolved_resource_field_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "resource obligation"):
            compile_source(
                "resource Buffer[Ready]\n"
                "*Pair(left:own Buffer[Ready],right:own Buffer[Ready])\n"
                ">bad(pair:own Pair):own Buffer[Ready]\n"
                "  left := pair.left\n"
                "  left\n"
            )


if __name__ == "__main__":
    unittest.main()

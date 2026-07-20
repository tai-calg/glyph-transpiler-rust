from __future__ import annotations

import unittest

from glyph import compile_source


class GuardSpacingTests(unittest.TestCase):
    def test_guard_arrow_accepts_compact_and_spaced_forms(self) -> None:
        compact = compile_source(
            ">f(x:I):I\n"
            "  x<0>>-1\n"
            "  _>>0\n"
        )
        spaced = compile_source(
            ">f(x:I):I\n"
            "  x<0 >> -1\n"
            "  _ >> 0\n"
        )
        self.assertEqual(compact, spaced)


if __name__ == "__main__":
    unittest.main()

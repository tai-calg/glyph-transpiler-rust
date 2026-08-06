from __future__ import annotations

import unittest

from glyph.preprocessor import preprocess_source


class MacroDefinitionCompatibilityTests(unittest.TestCase):
    def test_legacy_equals_macro_keeps_spaces_in_replacement(self) -> None:
        result = preprocess_source("@EDGE=sensor -> ctl\nEDGE\n")
        self.assertEqual(result.source, "sensor -> ctl\n")

    def test_legacy_equals_macro_keeps_expression_spacing(self) -> None:
        result = preprocess_source("@EXPR=x + y * z\n>f(x:I,y:I,z:I):I=EXPR\n")
        self.assertEqual(result.source, ">f(x:I,y:I,z:I):I=x + y * z\n")

    def test_canonical_replacement_can_start_with_equals(self) -> None:
        result = preprocess_source("@ALIAS =Count=U\nALIAS\n")
        self.assertEqual(result.source, "=Count=U\n")


if __name__ == "__main__":
    unittest.main()

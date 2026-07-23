from __future__ import annotations

import unittest

from glyph.verification_classes import split_verification_classes


class VerificationClassTests(unittest.TestCase):
    def test_classes_are_validated_and_deduplicated(self) -> None:
        self.assertEqual(
            split_verification_classes("static+trusted+static"),
            ("static", "trusted"),
        )

    def test_unknown_class_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown verification classes"):
            split_verification_classes("static+assumed")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from glyph.diagnostic_localization import localize_diagnostic, localize_state_views


class DiagnosticLocalizationTests(unittest.TestCase):
    def test_ambiguous_trigger_has_japanese_and_english_messages(self) -> None:
        item = localize_diagnostic(
            {
                "severity": "warning",
                "code": "STIR_TRIGGER_AMBIGUOUS_FALLBACK",
                "message": (
                    "`input.forced_open` is input-derived, but the compiler cannot "
                    "determine whether it represents an occurrence or a persistent condition."
                ),
                "line": 12,
            }
        )

        self.assertIn("出来事", item["message_ja"])
        self.assertIn("暫定的に入力", item["message_ja"])
        self.assertIn("input.forced_open", item["message_en"])
        self.assertIn("直和型", item["help_ja"])

    def test_unreachable_state_is_localized_without_losing_original(self) -> None:
        item = localize_diagnostic(
            {
                "severity": "warning",
                "code": "unreachable-state",
                "message": "state Faulted is unreachable from initial state Locked",
                "line": 4,
            }
        )

        self.assertEqual(
            item["message_ja"],
            "状態 `Faulted` は初期状態 `Locked` から到達できません。",
        )
        self.assertEqual(
            item["message_en"],
            "state Faulted is unreachable from initial state Locked",
        )

    def test_views_declare_japanese_as_default_locale(self) -> None:
        views = localize_state_views(
            {
                "state": {
                    "machines": [
                        {
                            "diagnostics": [
                                {
                                    "severity": "warning",
                                    "code": "missing-default",
                                    "message": "missing fallback",
                                    "line": 8,
                                }
                            ],
                            "transitions": [],
                        }
                    ]
                }
            }
        )

        self.assertEqual(views["locales"]["default"], "ja")
        self.assertEqual(views["locales"]["supported"], ["ja", "en"])
        diagnostic = views["state"]["machines"][0]["diagnostics"][0]
        self.assertIn("default節", diagnostic["message_ja"])


if __name__ == "__main__":
    unittest.main()

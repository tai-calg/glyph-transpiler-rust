from __future__ import annotations

from pathlib import Path
import unittest

from glyph.diagnostic_i18n import (
    localize_message_payload,
    translate_diagnostic_message,
)
from glyph.studio import STUDIO_HTML, StudioSnapshot


class DiagnosticI18nTests(unittest.TestCase):
    def test_common_compiler_messages_are_translated_deterministically(self) -> None:
        self.assertEqual(
            translate_diagnostic_message("line 12: unexpected identifier"),
            "12行目: 予期しない 識別子",
        )
        self.assertEqual(
            translate_diagnostic_message("expected return type, got value"),
            "戻り値型 が必要だが、値 が指定されている",
        )
        self.assertEqual(
            translate_diagnostic_message("型 `DoorState` が必要"),
            "型 `DoorState` が必要",
        )

    def test_recursive_payload_preserves_canonical_message_and_adds_locales(self) -> None:
        payload = localize_message_payload(
            {
                "diagnostics": [
                    {"severity": "error", "message": "unexpected identifier"}
                ],
                "views": {
                    "state": {
                        "machines": [
                            {
                                "diagnostics": [
                                    {
                                        "severity": "warning",
                                        "message": "unreachable state",
                                    }
                                ]
                            }
                        ]
                    }
                },
            }
        )
        top = payload["diagnostics"][0]
        nested = payload["views"]["state"]["machines"][0]["diagnostics"][0]
        self.assertEqual(top["message"], "unexpected identifier")
        self.assertEqual(top["message_en"], "unexpected identifier")
        self.assertEqual(top["message_ja"], "予期しない 識別子")
        self.assertEqual(nested["message_ja"], "到達不能な 状態")

    def test_studio_snapshot_api_exposes_bilingual_diagnostics(self) -> None:
        snapshot = StudioSnapshot(
            version=1,
            status="error",
            source="",
            digest="digest",
            updated_at="now",
            diagnostics=(
                {"severity": "error", "message": "unexpected identifier"},
            ),
            artifacts={},
            semantic={},
            execution_ir={},
            glyph04_views={},
        )
        payload = snapshot.to_dict(Path("example.glyph"), Path(".glyph/example"))
        diagnostic = payload["diagnostics"][0]
        self.assertEqual(diagnostic["message_en"], "unexpected identifier")
        self.assertEqual(diagnostic["message_ja"], "予期しない 識別子")

    def test_studio_ui_defaults_to_japanese_and_offers_english(self) -> None:
        self.assertIn("glyph-studio-locale-v1-script", STUDIO_HTML)
        self.assertIn('DEFAULT_LOCALE="ja"', STUDIO_HTML)
        self.assertIn('id="glyph-language-select"', STUDIO_HTML)
        self.assertIn('<option value="ja">日本語</option>', STUDIO_HTML)
        self.assertIn('<option value="en">English</option>', STUDIO_HTML)


if __name__ == "__main__":
    unittest.main()

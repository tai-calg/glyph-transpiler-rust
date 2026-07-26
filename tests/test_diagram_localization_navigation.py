from __future__ import annotations

from pathlib import Path
import unittest

from glyph import diagram_app
from glyph.diagram_app import DiagramSnapshot
from glyph.diagram_canvas_navigation import enhance_diagram_canvas_navigation_html
from glyph.diagram_locale import enhance_diagram_locale_html
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app


class DiagramLocalizationNavigationTests(unittest.TestCase):
    def test_diagram_ui_defaults_to_japanese_and_offers_english(self) -> None:
        html = enhance_diagram_locale_html(DIAGRAM_HTML)
        self.assertIn("glyph-diagram-locale-v1-script", html)
        self.assertIn('DEFAULT_LOCALE="ja"', html)
        self.assertIn('id="glyph-diagram-language-select"', html)
        self.assertIn('<option value="ja">日本語</option>', html)
        self.assertIn('<option value="en">English</option>', html)

    def test_blank_canvas_drag_pans_with_reachable_gutter(self) -> None:
        html = enhance_diagram_canvas_navigation_html(DIAGRAM_HTML)
        self.assertIn("glyph-diagram-canvas-navigation-v1-script", html)
        self.assertIn("--glyph-pan-gutter:220px", html)
        self.assertIn("shell.setPointerCapture", html)
        self.assertIn("shell.scrollLeft=drag.left", html)
        self.assertIn("空白をドラッグしてキャンバスを移動", html)
        self.assertIn("overscroll-behavior:contain", html)

    def test_prepared_app_contains_locale_and_pan_layers(self) -> None:
        prepare_diagram_app()
        self.assertIn("glyph-diagram-locale-v1-script", diagram_app.DIAGRAM_HTML)
        self.assertIn(
            "glyph-diagram-canvas-navigation-v1-script",
            diagram_app.DIAGRAM_HTML,
        )

    def test_diagram_snapshot_api_exposes_bilingual_nested_diagnostics(self) -> None:
        prepare_diagram_app()
        snapshot = DiagramSnapshot(
            version=1,
            status="error",
            source="",
            digest="digest",
            updated_at="now",
            diagnostics=(
                {"severity": "error", "message": "unexpected identifier"},
            ),
            views={
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
        )
        payload = snapshot.to_dict(Path("example.glyph"), Path("views.json"))
        self.assertEqual(
            payload["diagnostics"][0]["message_ja"],
            "予期しない 識別子",
        )
        self.assertEqual(
            payload["views"]["state"]["machines"][0]["diagnostics"][0][
                "message_ja"
            ],
            "到達不能な 状態",
        )


if __name__ == "__main__":
    unittest.main()

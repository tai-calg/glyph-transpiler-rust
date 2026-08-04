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
        self.assertIn('const STORAGE_KEY="glyph.ui.locale"', html)
        self.assertIn('?localStorage.getItem(STORAGE_KEY):"ja"', html.replace(" ", ""))
        self.assertIn('id="glyph-language"', html)
        self.assertIn('<option value="ja">日本語</option>', html)
        self.assertIn('<option value="en">English</option>', html)
        self.assertIn('glyph-locale-change', html)
        self.assertIn('glyph-locale-changed', html)
        self.assertNotIn("空白をドラッグしてキャンバス", html)
        self.assertNotIn("Drag an empty area to pan", html)
        self.assertIn('shell.removeAttribute("title")', html)

    def test_blank_canvas_drag_pans_without_help_overlay(self) -> None:
        html = enhance_diagram_canvas_navigation_html(DIAGRAM_HTML)
        self.assertIn("glyph-diagram-canvas-navigation-v1-script", html)
        self.assertIn("--glyph-pan-gutter:220px", html)
        self.assertIn("shell.setPointerCapture", html)
        self.assertIn("desiredX", html)
        self.assertIn("residualY", html)
        self.assertIn('shell.closest(".view-body")', html)
        self.assertNotIn("空白をドラッグしてキャンバスを移動", html)
        self.assertNotIn("Drag empty canvas to pan", html)
        self.assertNotIn(".canvas-pan-help{", html)
        self.assertIn('querySelector(":scope > .canvas-pan-help")?.remove()', html)
        self.assertIn('shell.removeAttribute("title")', html)
        self.assertIn("overscroll-behavior:contain", html)
        self.assertIn("sessionStorage", html)

    def test_prepared_app_contains_locale_pan_and_viewport_layers(self) -> None:
        prepare_diagram_app()
        self.assertIn("glyph-diagram-locale-v1-script", diagram_app.DIAGRAM_HTML)
        self.assertIn(
            "glyph-diagram-canvas-navigation-v1-script",
            diagram_app.DIAGRAM_HTML,
        )
        self.assertIn(
            "glyph-diagram-canvas-viewport-v1-script",
            diagram_app.DIAGRAM_HTML,
        )

    def test_diagram_snapshot_api_exposes_bilingual_nested_diagnostics(self) -> None:
        prepare_diagram_app()
        snapshot = DiagramSnapshot(
            version=1,
            status="error",
            source="",
            digest="digest",
            rendered_digest="previous-digest",
            last_successful_version=0,
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
        self.assertEqual(payload["rendered_digest"], "previous-digest")
        self.assertEqual(
            payload["diagnostics"][0]["message_ja"],
            "予期しない識別子",
        )
        self.assertEqual(
            payload["views"]["state"]["machines"][0]["diagnostics"][0][
                "message_ja"
            ],
            "到達不能な状態",
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_canvas_navigation import enhance_diagram_canvas_navigation_html
from glyph.diagram_label_editor import enhance_diagram_label_editor_html
from glyph.diagram_locale import enhance_diagram_locale_html
from glyph.diagram_ui import DIAGRAM_HTML


class DiagramLocaleNavigationTests(unittest.TestCase):
    def test_locale_defaults_to_japanese_and_offers_english(self) -> None:
        html = enhance_diagram_locale_html(DIAGRAM_HTML)
        compact = html.replace(" ", "")

        self.assertIn("glyph-diagram-locale-v1", html)
        self.assertIn('value="ja">日本語', html)
        self.assertIn('value="en">English', html)
        self.assertIn('localStorage.getItem(STORAGE_KEY)', html)
        self.assertIn('?localStorage.getItem(STORAGE_KEY):"ja"', compact)
        self.assertIn('`message_${locale}`', html)
        self.assertIn('`help_${locale}`', html)
        self.assertIn('const STORAGE_KEY="glyph.ui.locale"', html)

    def test_canvas_navigation_hands_residual_scroll_to_preview(self) -> None:
        html = enhance_diagram_canvas_navigation_html(DIAGRAM_HTML)

        self.assertIn("glyph-diagram-canvas-navigation-v1", html)
        self.assertIn("residualY", html)
        self.assertIn('shell.closest(".view-body")', html)
        self.assertIn("glyph-panning", html)

    def test_label_editor_limits_distance_from_arrow_midpoint(self) -> None:
        html = enhance_diagram_label_editor_html(DIAGRAM_HTML)

        self.assertIn("glyph-diagram-label-editor-v2", html)
        self.assertIn("MAX_DISTANCE=96", html)
        self.assertIn("getPointAtLength(length/2)", html)
        self.assertIn("project(point,anchor", html)
        self.assertIn("collisionCount", html)
        self.assertNotIn("railY", html)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_all_injected_javascript_is_syntactically_valid(self) -> None:
        html = DIAGRAM_HTML
        for enhancer in (
            enhance_diagram_label_editor_html,
            enhance_diagram_canvas_navigation_html,
            enhance_diagram_locale_html,
        ):
            html = enhancer(html)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "diagram-locale-navigation.js"
            script.write_text("\n".join(scripts), encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(script)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

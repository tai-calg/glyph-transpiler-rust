from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_ui import DIAGRAM_HTML
from glyph.transition_label_layout import enhance_diagram_html


class TransitionLabelLayoutTests(unittest.TestCase):
    def test_layout_layer_is_idempotent_and_contains_required_views(self) -> None:
        enhanced = enhance_diagram_html(DIAGRAM_HTML)
        self.assertEqual(enhance_diagram_html(enhanced), enhanced)
        for marker in (
            "glyph-transition-label-layout-v1",
            "Transition details",
            "transition-detail-condition",
            "placeLabels",
            "layout-fallback",
            "glyph-transition-layout-ready",
        ):
            self.assertIn(marker, enhanced)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        enhanced = enhance_diagram_html(DIAGRAM_HTML)
        match = re.search(
            r'<script id="glyph-transition-label-layout-v1-script">(.*?)</script>',
            enhanced,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "transition-label-layout.js"
            script.write_text(match.group(1), encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(script)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

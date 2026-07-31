from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_canvas_viewport import enhance_diagram_canvas_viewport_html
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.layout_corridor_fast_repair import enhance_layout_corridor_fast_repair_html
from glyph.layout_corridor_repair import enhance_layout_corridor_repair_html
from glyph.layout_local_repair import enhance_layout_local_repair_html
from glyph.layout_shelf_repair import enhance_layout_shelf_repair_html
from glyph.layout_shelf_viewport_sync import enhance_layout_shelf_viewport_sync_html


class LayoutShelfViewportSyncTests(unittest.TestCase):
    def _html(self) -> str:
        return enhance_layout_shelf_viewport_sync_html(
            enhance_layout_shelf_repair_html(
                enhance_layout_corridor_fast_repair_html(
                    enhance_layout_corridor_repair_html(
                        enhance_layout_local_repair_html(
                            enhance_diagram_canvas_viewport_html(DIAGRAM_HTML)
                        )
                    )
                )
            )
        )

    def test_sync_refits_only_fit_mode_without_viewport_change(self) -> None:
        html = self._html()

        self.assertIn("glyph-layout-shelf-viewport-sync-v1", html)
        self.assertIn('mode && mode !== "fit"', html)
        self.assertIn("await silentFit(stage)", html)
        self.assertIn("await nextPaint()", html)
        self.assertIn("glyph.diagram.viewport-mode.v1", html)
        self.assertNotIn("glyph-diagram-viewport-change", html)
        self.assertIn("result?.shelfRerouted", html)
        self.assertIn("base.version = 6", html)

    def test_enhancer_is_idempotent(self) -> None:
        once = self._html()
        twice = enhance_layout_shelf_viewport_sync_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", self._html(), re.DOTALL)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "layout-shelf-viewport-sync.js"
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

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_geometry_kernel import enhance_diagram_geometry_kernel_html
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.layout_corridor_repair import enhance_layout_corridor_repair_html
from glyph.layout_local_repair import enhance_layout_local_repair_html


class LayoutCorridorRepairTests(unittest.TestCase):
    def _html(self) -> str:
        return enhance_layout_corridor_repair_html(
            enhance_layout_local_repair_html(
                enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)
            )
        )

    def test_corridor_repair_wraps_local_repair_without_weakening_certificate(self) -> None:
        html = self._html()

        self.assertIn("glyph-layout-corridor-repair-v1", html)
        self.assertIn("layout-corridor-repair-failed", html)
        self.assertIn("minimumClearance: INITIAL_CLEARANCE", html)
        self.assertIn("geom.polylineHitsRect(points, item.rect)", html)
        self.assertIn("outer route lanes have no joint assignment", html)
        self.assertIn("if (!shouldEscalate(error)) throw error", html)
        self.assertIn("manualConflicts", html)
        self.assertIn("base.version = 3", html)
        self.assertIn("corridorRerouted = true", html)

    def test_enhancer_is_idempotent(self) -> None:
        once = self._html()
        twice = enhance_layout_corridor_repair_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", self._html(), re.DOTALL)
        self.assertGreaterEqual(len(scripts), 4)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "layout-corridor-repair.js"
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

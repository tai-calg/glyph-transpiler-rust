from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_geometry_kernel import enhance_diagram_geometry_kernel_html
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.layout_corridor_fast_repair import enhance_layout_corridor_fast_repair_html
from glyph.layout_corridor_repair import enhance_layout_corridor_repair_html
from glyph.layout_local_repair import enhance_layout_local_repair_html


class LayoutCorridorFastRepairTests(unittest.TestCase):
    def _html(self) -> str:
        return enhance_layout_corridor_fast_repair_html(
            enhance_layout_corridor_repair_html(
                enhance_layout_local_repair_html(
                    enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)
                )
            )
        )

    def test_dense_repair_is_bounded_and_fail_closed(self) -> None:
        html = self._html()

        self.assertIn("glyph-layout-corridor-fast-repair-v1", html)
        self.assertIn("paths >= 8", html)
        self.assertIn("Math.ceil(paths / 2)", html)
        self.assertIn("MAX_ROUTE_STEPS = 24000", html)
        self.assertIn("MAX_LABEL_STEPS = 120000", html)
        self.assertIn("minimumClearance: INITIAL_CLEARANCE", html)
        self.assertIn("corridor placement failed transaction audit", html)
        self.assertIn("for (const [path, snapshot] of pathSnapshots)", html)
        self.assertIn("base.version = 4", html)

    def test_enhancer_is_idempotent(self) -> None:
        once = self._html()
        twice = enhance_layout_corridor_fast_repair_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", self._html(), re.DOTALL)
        self.assertGreaterEqual(len(scripts), 5)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "layout-corridor-fast-repair.js"
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

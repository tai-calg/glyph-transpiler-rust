from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_geometry_kernel import enhance_diagram_geometry_kernel_html
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.layout_local_repair import enhance_layout_local_repair_html


class LayoutLocalRepairTests(unittest.TestCase):
    def test_repair_is_dirty_set_bounded_and_frame_budgeted(self) -> None:
        html = enhance_layout_local_repair_html(
            enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)
        )

        self.assertIn("glyph-layout-local-repair-v1", html)
        self.assertIn("route-foreign-label", html)
        self.assertIn("dirtyIds", html)
        self.assertIn("FRAME_BUDGET_MS = 8", html)
        self.assertIn("runBudgeted(candidates", html)
        self.assertIn("MAX_STEPS = 80000", html)
        self.assertIn("manual label positions violate publication geometry", html)
        self.assertIn("path.id !== entry.id", html)
        self.assertIn('stage.dataset.layoutLocalRepairState = "repaired"', html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_layout_local_repair_html(DIAGRAM_HTML)
        twice = enhance_layout_local_repair_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_layout_local_repair_html(
            enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)
        )
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        self.assertGreaterEqual(len(scripts), 3)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "layout-local-repair.js"
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

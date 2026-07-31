from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_geometry_kernel import enhance_diagram_geometry_kernel_html
from glyph.diagram_ui import DIAGRAM_HTML


class DiagramGeometryKernelTests(unittest.TestCase):
    def test_kernel_exposes_certified_geometry_and_budget_primitives(self) -> None:
        html = enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)

        self.assertIn("glyph-diagram-geometry-kernel-v1", html)
        self.assertIn("flattenPathData", html)
        self.assertIn("flattenPathElement", html)
        self.assertIn("verifyPathData", html)
        self.assertIn("verifyPathElement", html)
        self.assertIn("minimumPolylineDistance", html)
        self.assertIn("polylineHitsRect", html)
        self.assertIn("runBudgeted", html)
        self.assertIn("findBudgeted", html)
        self.assertIn("pathCacheHits", html)
        self.assertIn("maxSliceMs", html)

    def test_kernel_is_idempotent(self) -> None:
        once = enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)
        twice = enhance_diagram_geometry_kernel_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        self.assertGreaterEqual(len(scripts), 2)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "diagram-geometry-kernel.js"
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

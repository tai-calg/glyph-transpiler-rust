from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_render_stability import enhance_diagram_render_stability_html
from glyph.diagram_ui import DIAGRAM_HTML


class DiagramRenderStabilityTests(unittest.TestCase):
    def test_enhancer_suppresses_unchanged_render_and_hides_pending_state_graph(self) -> None:
        html = enhance_diagram_render_stability_html(DIAGRAM_HTML)

        self.assertIn("glyph-diagram-render-stability-v1", html)
        self.assertIn('stage.dataset.renderStable = "true"', html)
        self.assertIn("diagram-render-pending", html)
        self.assertIn("lastRenderKey", html)
        self.assertIn("REQUIRED_FLAGS", html)
        self.assertIn("stateTransitionIRV2LabelsReady", html)
        self.assertIn("initialRouteReady", html)
        self.assertIn("Rendering adjusted state diagram", html)
        self.assertIn("visibility:hidden!important", html)
        self.assertIn("key === lastRenderKey", html)
        self.assertIn("requestAnimationFrame(() => requestAnimationFrame", html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_diagram_render_stability_html(DIAGRAM_HTML)
        twice = enhance_diagram_render_stability_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_diagram_render_stability_html(DIAGRAM_HTML)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "diagram-render-stability.js"
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

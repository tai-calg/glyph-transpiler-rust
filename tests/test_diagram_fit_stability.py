from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_canvas_viewport import enhance_diagram_canvas_viewport_html
from glyph.diagram_fit_stability import enhance_diagram_fit_stability_html
from glyph.diagram_ui import DIAGRAM_HTML


class DiagramFitStabilityTests(unittest.TestCase):
    def _html(self) -> str:
        return enhance_diagram_fit_stability_html(
            enhance_diagram_canvas_viewport_html(DIAGRAM_HTML)
        )

    def test_fit_stability_is_state_only_and_certifies_visible_elements(self) -> None:
        html = self._html()
        injected = re.search(
            r'<script id="glyph-diagram-fit-stability-v1-script">(.*?)</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(injected)
        assert injected is not None
        script = injected.group(1)

        self.assertIn("glyph-diagram-fit-stability-v1", html)
        self.assertIn('dataset.tab !== "state"', script)
        self.assertIn("new ResizeObserver", script)
        self.assertIn("canvas-shell-resize", script)
        self.assertIn("diagnostics-resize", script)
        self.assertIn("transitionPublicationReady", script)
        self.assertIn("layoutCertificateState", script)
        self.assertIn("visibilityAudit", script)
        self.assertIn("visibleShellBounds", script)
        self.assertIn("window.innerHeight", script)
        self.assertIn(".state-node", script)
        self.assertIn(".transition-io-cluster", script)
        self.assertNotIn(".graph-node", script)
        self.assertNotIn("glyph-diagram-viewport-change", script)
        self.assertIn('fitVisibilityState = "failed"', script)
        self.assertIn('fitVisibilityState = "ready"', script)

    def test_enhancer_is_idempotent(self) -> None:
        once = self._html()
        twice = enhance_diagram_fit_stability_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", self._html(), re.DOTALL)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "diagram-fit-stability.js"
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

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_ui import DIAGRAM_HTML
from glyph.state_transition_ir_renderer import enhance_state_transition_ir_html


class StateTransitionIRRendererTests(unittest.TestCase):
    def test_renderer_uses_structured_failure_type(self) -> None:
        html = enhance_state_transition_ir_html(DIAGRAM_HTML)

        self.assertIn("glyph-state-transition-ir-v2-renderer", html)
        self.assertIn("transition?.failure_type", html)
        self.assertIn("`${action} | ${failure}`", html)
        self.assertNotIn("const suffix = ` ! ${failureType}`", html)
        self.assertIn('stage.dataset.stateTransitionIRV2LabelsReady = "true"', html)

    def test_renderer_is_idempotent(self) -> None:
        once = enhance_state_transition_ir_html(DIAGRAM_HTML)
        twice = enhance_state_transition_ir_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_state_transition_ir_html(DIAGRAM_HTML)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        self.assertGreaterEqual(len(scripts), 2)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "state-transition-ir-renderer.js"
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

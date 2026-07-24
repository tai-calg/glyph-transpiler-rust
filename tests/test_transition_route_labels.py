from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_ui import DIAGRAM_HTML
from glyph.transition_route_labels import enhance_transition_route_html


class TransitionInputActionLabelTests(unittest.TestCase):
    def test_compact_labels_use_input_to_action_not_internal_ids_or_routes(self) -> None:
        html = enhance_transition_route_html(DIAGRAM_HTML)

        self.assertIn("glyph-transition-input-action-labels-v2", html)
        self.assertIn("function inputOf(transition)", html)
        self.assertIn("function actionOf(transition)", html)
        self.assertIn("return `${inputOf(transition)}➡︎${actionOf(transition)}`", html)
        self.assertIn('label?.classList.contains("compact")', html)
        self.assertNotIn("source_state ??", html)
        self.assertNotIn("target_state ??", html)

    def test_state_label_enhancer_does_not_modify_io_rendering(self) -> None:
        html = enhance_transition_route_html(DIAGRAM_HTML)

        self.assertIn(">connects</span>", html)
        self.assertIn("port-title", html)
        self.assertIn("port-dot", html)
        self.assertNotIn("glyph-direct-io-layout", html)
        self.assertNotIn("ioContractReady", html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_transition_route_html(DIAGRAM_HTML)
        twice = enhance_transition_route_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_transition_route_html(DIAGRAM_HTML)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        self.assertGreaterEqual(len(scripts), 2)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "transition-input-action.js"
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
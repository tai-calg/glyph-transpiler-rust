from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_ui import DIAGRAM_HTML
from glyph.failure_result_labels import enhance_failure_result_html


class FailureResultLabelTests(unittest.TestCase):
    def test_enhancer_uses_pipe_not_effect_sigil_for_failure_result(self) -> None:
        html = enhance_failure_result_html(DIAGRAM_HTML)

        self.assertIn("glyph-failure-result-labels-v1", html)
        self.assertIn('const suffix = ` ! ${failureType}`', html)
        self.assertIn('`${text.slice(0, -suffix.length)} | ${failureType}`', html)
        self.assertIn('stage.dataset.failureResultNotationReady = "true"', html)
        self.assertIn("transition.synthesized_failure", html)
        self.assertIn("transition.failure_type", html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_failure_result_html(DIAGRAM_HTML)
        twice = enhance_failure_result_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_failure_result_html(DIAGRAM_HTML)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        self.assertGreaterEqual(len(scripts), 2)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "failure-result-labels.js"
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

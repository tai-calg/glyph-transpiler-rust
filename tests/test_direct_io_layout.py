from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_ui import DIAGRAM_HTML
from glyph.direct_io_layout import enhance_direct_io_html


class DirectIoLayoutTests(unittest.TestCase):
    def test_enhancer_removes_connection_labels_and_preserves_full_contracts(self) -> None:
        html = enhance_direct_io_html(DIAGRAM_HTML)

        self.assertIn("glyph-direct-io-layout-v1", html)
        self.assertIn('label.textContent?.trim() === "connects"', html)
        self.assertIn('marker.textContent = direction', html)
        self.assertIn('direction = index === 0 ? "IN" : "OUT"', html)
        self.assertIn("text-overflow:clip", html)
        self.assertIn("white-space:normal", html)
        self.assertIn('stage.dataset.ioContractReady = "true"', html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_direct_io_html(DIAGRAM_HTML)
        twice = enhance_direct_io_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_direct_io_html(DIAGRAM_HTML)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        self.assertGreaterEqual(len(scripts), 2)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "direct-io.js"
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

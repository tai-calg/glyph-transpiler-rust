from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.code_derived_system_ui import enhance_code_derived_system_html
from glyph.diagram_ui import DIAGRAM_HTML


class ExecutableSystemBoundaryUiTests(unittest.TestCase):
    def test_enhancer_explains_entry_source_sink_and_call_edges(self) -> None:
        html = enhance_code_derived_system_html(DIAGRAM_HTML)
        self.assertIn("glyph-executable-system-boundary-ui-v3", html)
        self.assertIn("完全な関数実行境界", html)
        self.assertIn("Executable System boundary", html)
        self.assertIn("Entry:", html)
        self.assertIn("Sources:", html)
        self.assertIn("Sinks:", html)
        self.assertIn("Calls:", html)
        self.assertIn('edges[index]?.label || "calls"', html)
        self.assertIn("boundary-entry", html)
        self.assertIn("boundary-source", html)
        self.assertIn("boundary-sink", html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_code_derived_system_html(DIAGRAM_HTML)
        twice = enhance_code_derived_system_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_code_derived_system_html(DIAGRAM_HTML)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "executable-system-boundary-ui.js"
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

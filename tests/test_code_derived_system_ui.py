from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.code_derived_system_ui import enhance_code_derived_system_html
from glyph.diagram_ui import DIAGRAM_HTML


class CodeDerivedSystemUiTests(unittest.TestCase):
    def test_enhancer_explains_derived_systems_and_call_edges(self) -> None:
        html = enhance_code_derived_system_html(DIAGRAM_HTML)
        self.assertIn("glyph-code-derived-system-ui-v1", html)
        self.assertIn("実際の関数呼出しを追跡", html)
        self.assertIn("Derived from code", html)
        self.assertIn("Entry:", html)
        self.assertIn('edges[index]?.label || "calls"', html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_code_derived_system_html(DIAGRAM_HTML)
        twice = enhance_code_derived_system_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_code_derived_system_html(DIAGRAM_HTML)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "code-derived-system-ui.js"
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

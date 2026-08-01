from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_ui import DIAGRAM_HTML
from glyph.layout_dependency_bridge import enhance_layout_dependency_bridge_html


class LayoutDependencyBridgeTests(unittest.TestCase):
    def test_transaction_claims_exclusive_layout_scheduling(self) -> None:
        html = enhance_layout_dependency_bridge_html(DIAGRAM_HTML)

        self.assertIn("glyph-layout-dependency-bridge-v1", html)
        self.assertIn("claimTransactionOwnership", html)
        self.assertIn("control.ownsScheduling = true", html)
        self.assertIn("transaction?.ownsScheduling !== true", html)
        self.assertIn("glyph-transition-layout-transaction-ready", html)
        self.assertIn("glyph-layout-local-repair-ready", html)
        self.assertIn('window.glyphInitialTransitionRouter?.schedule?.("layout-local-repair", 0)', html)

    def test_last_certified_layout_remains_hit_testable_during_recompute(self) -> None:
        html = enhance_layout_dependency_bridge_html(DIAGRAM_HTML)

        self.assertIn('data-transition-layout-published-once="true"', html)
        self.assertIn('data-transition-layout-state="pending"', html)
        self.assertIn('data-transition-publication-ready="false"', html)
        self.assertIn("visibility:visible!important", html)
        self.assertIn("pointer-events:auto!important", html)
        self.assertIn("markPublishedLayout", html)
        self.assertIn("glyph-layout-publication-certificate-ready", html)
        self.assertIn('stage.dataset.transitionLayoutPublishedOnce = "true"', html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_layout_dependency_bridge_html(DIAGRAM_HTML)
        twice = enhance_layout_dependency_bridge_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_layout_dependency_bridge_html(DIAGRAM_HTML)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "layout-dependency-bridge.js"
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

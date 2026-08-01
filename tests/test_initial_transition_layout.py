from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_geometry_kernel import enhance_diagram_geometry_kernel_html
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.initial_transition_layout import enhance_initial_transition_html


class InitialTransitionLayoutTests(unittest.TestCase):
    def test_enhancer_adds_certified_incremental_route_contract(self) -> None:
        html = enhance_initial_transition_html(
            enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)
        )

        self.assertIn("glyph-initial-transition-routing-v2", html)
        self.assertIn("glyph-diagram-geometry-kernel-v1", html)
        self.assertIn("initial-transition-path", html)
        self.assertIn("candidateRoutes(target)", html)
        self.assertIn("certifyCandidate(item, context)", html)
        self.assertIn("findBudgeted(ranked", html)
        self.assertIn("FRAME_BUDGET_MS = 8", html)
        self.assertIn("final SVG geometry failed post-commit certification", html)
        self.assertIn('stage.dataset.initialRouteCertificate = "valid"', html)
        self.assertIn('stage.dataset.initialRouteCacheHit = "true"', html)
        self.assertIn('target.classList.add("initial-target")', html)

    def test_cache_hit_and_fresh_route_share_one_completion_event(self) -> None:
        html = enhance_initial_transition_html(DIAGRAM_HTML)

        self.assertIn("function completeRoute(machine, token, details)", html)
        self.assertEqual(html.count("completeRoute(machine, token, {"), 2)
        self.assertEqual(
            html.count('new CustomEvent("glyph-initial-transition-route-ready"'),
            1,
        )
        self.assertIn("cacheHit: true", html)
        self.assertIn("cacheHit: false", html)
        self.assertIn("generation: token", html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_initial_transition_html(DIAGRAM_HTML)
        twice = enhance_initial_transition_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_initial_transition_html(
            enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)
        )
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        self.assertGreaterEqual(len(scripts), 3)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "initial-transition-layout.js"
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

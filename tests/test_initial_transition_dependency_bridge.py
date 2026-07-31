from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_ui import DIAGRAM_HTML
from glyph.initial_transition_dependency_bridge import (
    enhance_initial_transition_dependency_bridge_html,
)


class InitialTransitionDependencyBridgeTests(unittest.TestCase):
    def test_bridge_tracks_and_settles_final_rendered_geometry(self) -> None:
        html = enhance_initial_transition_dependency_bridge_html(DIAGRAM_HTML)

        self.assertIn("glyph-initial-transition-dependency-bridge-v2", html)
        self.assertIn('attributeFilter: ["class", "d", "transform"]', html)
        self.assertIn("normal-route-geometry-changed", html)
        self.assertIn("settleCertifiedRoute", html)
        self.assertIn("await nextFrame();\n    await nextFrame();", html)
        self.assertIn('stage.dataset.initialRouteReady = "settling"', html)
        self.assertIn('stage.dataset.initialRouteSettleState = "stable"', html)
        self.assertIn('stage.dataset.initialRouteReady = "certified"', html)
        self.assertNotIn('stage.dataset.initialRouteReady = "true"', html)
        self.assertIn("geom.verifyPathElement(initial, normals", html)
        self.assertIn("stable: true", html)
        self.assertIn(
            'glyphLayoutPublicationCertificate?.schedule?.("stable-initial-route", 0)',
            html,
        )

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_initial_transition_dependency_bridge_html(DIAGRAM_HTML)
        twice = enhance_initial_transition_dependency_bridge_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_initial_transition_dependency_bridge_html(DIAGRAM_HTML)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        self.assertGreaterEqual(len(scripts), 2)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "initial-transition-dependency-bridge.js"
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

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_ui import DIAGRAM_HTML
from glyph.transition_semantic_status_ui import (
    enhance_transition_semantic_status_ui_html,
)


class TransitionSemanticStatusUiTests(unittest.TestCase):
    def test_strict_projection_uses_explicit_visible_badge_class(self) -> None:
        html = enhance_transition_semantic_status_ui_html(DIAGRAM_HTML)

        self.assertIn("rtai-semantic-badge-visible", html)
        self.assertIn("display:inline-flex!important", html)
        self.assertIn('strict=projectionMode==="strict-exact"', html)
        self.assertIn(
            'cluster.classList.toggle("rtai-semantic-badge-visible",strict)',
            html,
        )
        self.assertIn(
            'cluster.classList.remove("rtai-semantic-badge-visible")',
            html,
        )

    def test_public_projection_mode_precedes_machine_compatibility_value(self) -> None:
        html = enhance_transition_semantic_status_ui_html(DIAGRAM_HTML)

        self.assertIn("function projectionModeOf(data,machine)", html)
        self.assertIn("text(data?.views?.rtai_projection_mode)", html)
        self.assertIn("text(machine?.analysis?.evidence_projection_mode)", html)
        self.assertIn("signatureOf(machine,projectionMode)", html)

    def test_ready_state_requires_bounded_layout_publication(self) -> None:
        html = enhance_transition_semantic_status_ui_html(DIAGRAM_HTML)

        self.assertIn("function publicationReady(stage)", html)
        self.assertIn('stage.dataset.transitionPublicationReady==="true"', html)
        self.assertIn('stage.dataset.transitionLayoutReady==="true"', html)
        self.assertIn('stage.dataset.rtaiSemanticStatusReady=published?"true":"pending"', html)
        self.assertIn("glyph-transition-layout-transaction-ready", html)
        self.assertNotIn("glyph-layout-publication-certificate-ready", html)
        self.assertNotIn("glyph-layout-publication-certificate-failed", html)
        self.assertIn("STATE_REQUEST_TIMEOUT_MS=48", html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_transition_semantic_status_ui_html(DIAGRAM_HTML)
        twice = enhance_transition_semantic_status_ui_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_transition_semantic_status_ui_html(DIAGRAM_HTML)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "transition-semantic-status-ui.js"
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

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_geometry_kernel import enhance_diagram_geometry_kernel_html
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.layout_publication_certificate import (
    enhance_layout_publication_certificate_html,
)


class LayoutPublicationCertificateTests(unittest.TestCase):
    def test_certificate_is_time_bounded_and_interactive(self) -> None:
        html = enhance_layout_publication_certificate_html(
            enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)
        )

        self.assertIn("glyph-layout-publication-certificate-v1", html)
        self.assertIn("function fingerprint(stage)", html)
        self.assertIn("layoutCertificateCacheHit", html)
        self.assertIn("TOTAL_BUDGET_MS = 32", html)
        self.assertIn('stage.dataset.transitionPublicationReady="false"', html)
        self.assertIn('stage.dataset.layoutCertificateState="valid"', html)
        self.assertIn('stage.dataset.layoutCertificateState="degraded"', html)
        self.assertIn('stage.dataset.layoutCertificateProfile="interactive-fast"', html)
        self.assertIn('layoutCertificateConstraints="structure,bounds,tether,initial-route-presence"', html)
        self.assertNotIn("runBudgeted(tasks", html)
        self.assertNotIn("route-foreign-label", html)
        self.assertNotIn("route-node", html)

    def test_degraded_certificate_keeps_the_diagram_publishable(self) -> None:
        html = enhance_layout_publication_certificate_html(
            enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)
        )

        degrade = re.search(
            r"function degrade\(stage,token,violations,metrics=\{\}\)\{(.*?)\n  \}",
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(degrade)
        assert degrade is not None
        body = degrade.group(1)
        self.assertIn('layoutCertificateState="degraded"', body)
        self.assertIn('transitionPublicationReady="true"', body)
        self.assertIn("glyph-layout-publication-certificate-failed", body)
        self.assertNotIn('initialRouteReady="failed"', body)

    def test_revalidation_is_queued_and_cancellable(self) -> None:
        html = enhance_layout_publication_certificate_html(
            enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)
        )

        self.assertIn('layoutCertificateRequestState="queued"', html)
        self.assertIn('layoutCertificateRequestState="running"', html)
        self.assertIn('layoutCertificateRequestState="completed"', html)
        self.assertIn('layoutCertificateRequestState="cancelled"', html)
        self.assertIn('layoutCertificateCacheHit=cacheHit?"true":"false"', html)
        self.assertIn('transitionPublicationReady="true"', html)
        self.assertIn("function cancel(reason=\"cancelled\")", html)
        self.assertIn('cancel("state-tab-deactivated")', html)
        self.assertIn("requestedGeneration+=1", html)
        self.assertIn("completedGeneration=requestedGeneration", html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_layout_publication_certificate_html(DIAGRAM_HTML)
        twice = enhance_layout_publication_certificate_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_layout_publication_certificate_html(
            enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)
        )
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        self.assertGreaterEqual(len(scripts), 3)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "layout-publication-certificate.js"
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

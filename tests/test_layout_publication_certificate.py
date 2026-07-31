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
    def test_certificate_is_incremental_budgeted_and_fail_closed(self) -> None:
        html = enhance_layout_publication_certificate_html(
            enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)
        )

        self.assertIn("glyph-layout-publication-certificate-v1", html)
        self.assertIn("geometryFingerprint(stage)", html)
        self.assertIn("layoutCertificateCacheHit", html)
        self.assertIn("runBudgeted(tasks", html)
        self.assertIn("FRAME_BUDGET_MS = 8", html)
        self.assertIn('stage.dataset.transitionPublicationReady = "false"', html)
        self.assertIn('stage.dataset.layoutCertificateState = "valid"', html)
        self.assertIn("route-foreign-label", html)
        self.assertIn("route-node", html)

    def test_revalidation_preserves_last_valid_certificate_until_fingerprint_check(self) -> None:
        html = enhance_layout_publication_certificate_html(
            enhance_diagram_geometry_kernel_html(DIAGRAM_HTML)
        )
        schedule = re.search(
            r"function schedule\(reason = \"scheduled\", delay = 0\) \{(.*?)\n  \}\n\n  for \(const eventName",
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(schedule)
        body = schedule.group(1)
        self.assertNotIn('layoutCertificateState = "pending"', body)
        self.assertIn('layoutCertificateRequestState = "queued"', body)
        self.assertIn('transitionPublicationReady = "false"', body)
        self.assertIn('layoutCertificateRequestState = "running"', html)
        self.assertIn('layoutCertificateRequestState = "completed"', html)
        self.assertIn('layoutCertificateCacheHit = "true"', html)
        self.assertIn('transitionPublicationReady = "true"', html)

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

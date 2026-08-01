from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_readable_exports import enhance_transition_readable_exports_html


class TransitionReadableExportTests(unittest.TestCase):
    def test_enhancer_exports_full_multiline_labels(self) -> None:
        html = enhance_transition_readable_exports_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-readable-exports-v1-script", html)
        self.assertIn("transition-io-export-label", html)
        self.assertIn("data-full-label", html)
        self.assertIn("<tspan", html)
        self.assertIn("font-size=\"${size}\"", html)
        self.assertIn("window.glyphReadableDiagramExports", html)
        self.assertIn("window.svg=svg", html)

    def test_prepared_app_installs_export_before_semantic_formatter(self) -> None:
        prepare_diagram_app()
        html = diagram_app.DIAGRAM_HTML
        exports = html.index("glyph-transition-readable-exports-v1-script")
        drag_guard = html.index("glyph-transition-label-drag-guard-v2-script")
        semantic = html.index("glyph-transition-readable-layout-v1-script")
        transaction = html.index("glyph-transition-layout-transaction-v1-script")
        self.assertGreater(exports, drag_guard)
        self.assertLess(exports, semantic)
        self.assertLess(exports, transaction)
        self.assertNotIn("glyph-transition-label-readability-v1-script", html)


if __name__ == "__main__":
    unittest.main()

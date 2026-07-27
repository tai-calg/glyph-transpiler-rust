from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_readable_layout import enhance_transition_readable_layout_html


class TransitionReadableLayoutTests(unittest.TestCase):
    def test_enhancer_uses_semantic_lines_and_dense_layout(self) -> None:
        html = enhance_transition_readable_layout_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-readable-layout-v1-script", html)
        self.assertIn("transition-semantic-line", html)
        self.assertIn("MAX_LINE=28", html)
        self.assertIn("word-break:normal!important", html)
        self.assertIn("overflow-wrap:normal!important", html)
        self.assertIn("DENSE_TRANSITIONS=7", html)
        self.assertIn("semanticDenseLayout", html)
        self.assertIn("glyphTransitionNodeLayoutGuard?.requestLayout", html)

    def test_prepared_app_installs_semantic_layout_last(self) -> None:
        prepare_diagram_app()
        html = diagram_app.DIAGRAM_HTML
        semantic = html.index("glyph-transition-readable-layout-v1-script")
        exports = html.index("glyph-transition-readable-exports-v1-script")
        readability = html.index("glyph-transition-label-readability-v1-script")
        self.assertGreater(semantic, exports)
        self.assertGreater(semantic, readability)
        self.assertIn("window.glyphTransitionReadableLayout", html)


if __name__ == "__main__":
    unittest.main()

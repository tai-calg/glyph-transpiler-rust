from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_readable_layout import enhance_transition_readable_layout_html


class TransitionReadableLayoutTests(unittest.TestCase):
    def test_enhancer_formats_semantic_lines_without_owning_node_layout(self) -> None:
        html = enhance_transition_readable_layout_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-readable-layout-v1-script", html)
        self.assertIn("transition-semantic-line", html)
        self.assertIn("MAX_LINE=28", html)
        self.assertIn("word-break:normal!important", html)
        self.assertIn("overflow-wrap:normal!important", html)
        self.assertIn("ownsNodeLayout:false", html)
        self.assertIn("ownsScheduling:false", html)
        self.assertIn("semantic-line-format-updated", html)
        self.assertIn("version:2", html)
        self.assertNotIn("DENSE_TRANSITIONS", html)
        self.assertNotIn("semanticDenseLayout", html)
        self.assertNotIn("node.style.left", html)
        self.assertNotIn("glyphTransitionNodeLayoutGuard?.requestLayout", html)
        self.assertNotIn("MutationObserver", html)

    def test_prepared_app_installs_semantic_formatter_last(self) -> None:
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

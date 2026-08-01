from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_dense_canvas_dimensions import (
    enhance_transition_dense_canvas_dimensions_html,
)


class TransitionDenseCanvasDimensionTests(unittest.TestCase):
    def test_legacy_enhancer_remains_available_but_is_expensive(self) -> None:
        html = enhance_transition_dense_canvas_dimensions_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-dense-canvas-dimensions-v1-script", html)
        self.assertIn("DENSE_TRANSITIONS=7", html)
        self.assertIn("MIN_WIDTH=1400", html)
        self.assertIn("MIN_HEIGHT=1000", html)
        self.assertIn("glyphTransitionIoCollisionSolver?.run", html)

    def test_interactive_app_excludes_dense_canvas_enhancer(self) -> None:
        prepare_diagram_app()
        html = diagram_app.DIAGRAM_HTML
        self.assertNotIn("glyph-transition-dense-canvas-dimensions-v1-script", html)
        self.assertNotIn("window.glyphTransitionDenseCanvasDimensions", html)
        self.assertIn("glyph-transition-layout-transaction-v1-script", html)
        self.assertIn('transitionDenseCanvas="disabled"', html)


if __name__ == "__main__":
    unittest.main()

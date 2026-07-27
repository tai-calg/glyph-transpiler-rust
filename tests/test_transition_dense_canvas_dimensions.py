from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_dense_canvas_dimensions import (
    enhance_transition_dense_canvas_dimensions_html,
)


class TransitionDenseCanvasDimensionTests(unittest.TestCase):
    def test_enhancer_keeps_dense_coordinate_domain_stable(self) -> None:
        html = enhance_transition_dense_canvas_dimensions_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-dense-canvas-dimensions-v1-script", html)
        self.assertIn("DENSE_TRANSITIONS=7", html)
        self.assertIn("MIN_WIDTH=1400", html)
        self.assertIn("MIN_HEIGHT=1000", html)
        self.assertIn("transitionDenseCanvas", html)
        self.assertIn("glyphTransitionIoCollisionSolver?.run", html)

    def test_prepared_app_installs_dimension_guard_last(self) -> None:
        prepare_diagram_app()
        html = diagram_app.DIAGRAM_HTML
        dimensions = html.index("glyph-transition-dense-canvas-dimensions-v1-script")
        role_lines = html.index("glyph-transition-semantic-role-lines-v1-script")
        self.assertGreater(dimensions, role_lines)
        self.assertIn("window.glyphTransitionDenseCanvasDimensions", html)


if __name__ == "__main__":
    unittest.main()

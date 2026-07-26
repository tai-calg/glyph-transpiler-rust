from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_canvas_viewport import enhance_diagram_canvas_viewport_html
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app


class DiagramCanvasViewportTests(unittest.TestCase):
    def test_enhancer_adds_zoom_fit_and_reset_controls(self) -> None:
        html = enhance_diagram_canvas_viewport_html(DIAGRAM_HTML)
        self.assertIn("glyph-diagram-canvas-viewport-v1-script", html)
        self.assertIn('id="diagram-zoom-out"', html)
        self.assertIn('id="diagram-zoom-in"', html)
        self.assertIn('id="diagram-fit"', html)
        self.assertIn('id="diagram-view-reset"', html)
        self.assertIn("MIN_SCALE=.25", html)
        self.assertIn("MAX_SCALE=3", html)
        self.assertIn("glyph-zoom-surface", html)
        self.assertIn("glyph.diagram.viewport-scale.v1:", html)
        self.assertIn("glyph.diagram.viewport-mode.v1:", html)
        self.assertIn("全体表示", html)
        self.assertIn("表示を戻す", html)

    def test_prepared_diagram_app_contains_viewport_layer(self) -> None:
        prepare_diagram_app()
        self.assertIn(
            "glyph-diagram-canvas-viewport-v1-script",
            diagram_app.DIAGRAM_HTML,
        )
        self.assertIn("window.glyphDiagramViewport", diagram_app.DIAGRAM_HTML)


if __name__ == "__main__":
    unittest.main()

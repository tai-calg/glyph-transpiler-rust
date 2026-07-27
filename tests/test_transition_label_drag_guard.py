from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_label_drag_guard import enhance_transition_label_drag_guard_html


class TransitionLabelDragGuardTests(unittest.TestCase):
    def test_enhancer_preserves_visible_manual_movement(self) -> None:
        html = enhance_transition_label_drag_guard_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-label-drag-guard-v1-script", html)
        self.assertIn("MIN_VISIBLE_MOVE=12", html)
        self.assertIn("transitionDragConstraint", html)
        self.assertIn("glyph.diagram.transition-io.v1:", html)
        self.assertIn("glyph-transition-label-manual-position", html)
        self.assertIn("glyphTransitionIoCollisionSolver?.run", html)

    def test_prepared_app_installs_drag_guard_after_layout_guards(self) -> None:
        prepare_diagram_app()
        html = diagram_app.DIAGRAM_HTML
        drag_guard = html.index("glyph-transition-label-drag-guard-v1-script")
        node_guard = html.index("glyph-transition-node-layout-guard-v1-script")
        readability = html.index("glyph-transition-label-readability-v1-script")
        self.assertGreater(drag_guard, node_guard)
        self.assertGreater(drag_guard, readability)
        self.assertIn("window.glyphTransitionLabelDragGuard", html)


if __name__ == "__main__":
    unittest.main()

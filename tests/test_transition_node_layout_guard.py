from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_node_layout_guard import (
    enhance_transition_node_layout_guard_html,
)


class TransitionNodeLayoutGuardTests(unittest.TestCase):
    def test_enhancer_preserves_nearest_feasible_node_position(self) -> None:
        html = enhance_transition_node_layout_guard_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-node-layout-guard-v1-script", html)
        self.assertIn("for(const ratio of[.75,.5,.25,0])", html)
        self.assertIn("glyphTransitionIoCollisionSolver?.run", html)
        self.assertIn("glyphTransitionLabelReadability?.repair", html)
        self.assertIn("glyph.diagram.positions.v1:", html)
        self.assertIn('transitionIoNodeConstraint="adjusted"', html)
        self.assertIn('transitionIoNodeConstraint="restored"', html)

    def test_prepared_app_installs_guard_after_readability(self) -> None:
        prepare_diagram_app()
        html = diagram_app.DIAGRAM_HTML
        guard = html.index("glyph-transition-node-layout-guard-v1-script")
        readability = html.index("glyph-transition-label-readability-v1-script")
        self.assertGreater(guard, readability)
        self.assertIn("window.glyphTransitionNodeLayoutGuard", html)


if __name__ == "__main__":
    unittest.main()

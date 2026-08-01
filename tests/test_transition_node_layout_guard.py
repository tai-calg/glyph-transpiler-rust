from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_node_layout_guard import (
    enhance_transition_node_layout_guard_html,
)


class TransitionNodeLayoutGuardTests(unittest.TestCase):
    def test_guard_delegates_without_owning_interaction_or_persistence(self) -> None:
        html = enhance_transition_node_layout_guard_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-node-layout-guard-v1-script", html)
        self.assertIn("const transaction=window.glyphTransitionLayoutTransaction", html)
        self.assertIn("transaction.schedule(reason,0)", html)
        self.assertIn('transitionIoNodeConstraint="delegated"', html)
        self.assertIn("ownsPointerEvents:false", html)
        self.assertIn("ownsPersistence:false", html)
        self.assertIn("ownsRouting:false", html)
        self.assertIn("version:2", html)
        self.assertNotIn('document.addEventListener("pointerdown"', html)
        self.assertNotIn('document.addEventListener("pointerup"', html)
        self.assertNotIn("localStorage.setItem", html)
        self.assertNotIn("function stateCurve(", html)

    def test_prepared_app_installs_passive_guard_after_readability(self) -> None:
        prepare_diagram_app()
        html = diagram_app.DIAGRAM_HTML
        guard = html.index("glyph-transition-node-layout-guard-v1-script")
        readability = html.index("glyph-transition-label-readability-v1-script")
        self.assertGreater(guard, readability)
        self.assertIn("window.glyphTransitionNodeLayoutGuard", html)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_label_drag_guard import enhance_transition_label_drag_guard_html


class TransitionLabelDragGuardTests(unittest.TestCase):
    def test_enhancer_is_passive_and_delegates_to_the_unified_owner(self) -> None:
        html = enhance_transition_label_drag_guard_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-label-drag-guard-v2-script", html)
        self.assertIn('interactionOwner:"glyph-transition-layout-interaction-adapter-v4"', html)
        self.assertIn("ownsPointerEvents:false", html)
        self.assertIn("ownsPersistence:false", html)
        self.assertIn("function invalidate(stage,reason)", html)
        self.assertIn('stage.dataset.manualLabelEditState="dragging"', html)
        self.assertIn('stage.dataset.transitionPublicationReady="false"', html)
        self.assertIn('stage.dataset.transitionIoCollisionSolved="editing"', html)
        self.assertIn('stage.dataset.layoutCertificateState="invalidated"', html)
        self.assertIn('stage.dataset.layoutCertificateRequestState="invalidated"', html)
        self.assertIn("glyphTransitionLayoutTransaction?.schedule?.(reason,0)", html)
        self.assertIn("version:3", html)
        self.assertNotIn('stage.dataset.transitionLayoutState="pending"', html)
        self.assertNotIn('addEventListener("pointerdown"', html)
        self.assertNotIn('addEventListener("pointerup"', html)
        self.assertNotIn("localStorage.setItem", html)

    def test_dragged_cluster_remains_interactive_while_publication_is_invalid(self) -> None:
        html = enhance_transition_label_drag_guard_html(DIAGRAM_HTML)

        self.assertIn('.transition-io-cluster.dragging-io', html)
        self.assertIn("visibility:visible!important", html)
        self.assertIn("pointer-events:auto!important", html)

    def test_prepared_app_installs_passive_guard_after_layout_guards(self) -> None:
        prepare_diagram_app()
        html = diagram_app.DIAGRAM_HTML
        drag_guard = html.index("glyph-transition-label-drag-guard-v2-script")
        node_guard = html.index("glyph-transition-node-layout-guard-v1-script")
        readability = html.index("glyph-transition-label-readability-v1-script")
        interaction = html.index("glyph-transition-layout-interaction-adapter-v1-script")
        self.assertGreater(drag_guard, node_guard)
        self.assertGreater(drag_guard, readability)
        self.assertGreater(interaction, drag_guard)
        self.assertIn("window.glyphTransitionLabelDragGuard", html)


if __name__ == "__main__":
    unittest.main()

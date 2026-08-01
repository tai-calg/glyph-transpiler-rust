from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_label_readability import (
    enhance_transition_label_readability_html,
)


class TransitionLabelReadabilityTests(unittest.TestCase):
    def test_legacy_enhancer_forbids_visual_truncation(self) -> None:
        html = enhance_transition_label_readability_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-label-readability-v1-script", html)
        self.assertIn("font-size:9px!important", html)
        self.assertIn("white-space:normal!important", html)
        self.assertIn("text-overflow:clip!important", html)
        self.assertIn("overflow-wrap:anywhere!important", html)
        self.assertNotIn("text-overflow:ellipsis!important", html)
        self.assertNotIn("font-size:5px!important", html)
        self.assertIn("transitionIoReadability", html)
        self.assertIn("horizontal-clipping", html)
        self.assertIn("vertical-clipping", html)
        self.assertIn("transition-io-export-label", html)
        self.assertIn("data-full-label", html)

    def test_interactive_app_uses_static_wrapping_without_search_layer(self) -> None:
        prepare_diagram_app()
        html = diagram_app.DIAGRAM_HTML
        self.assertNotIn("glyph-transition-label-readability-v1-style", html)
        self.assertNotIn("window.glyphTransitionLabelReadability", html)
        self.assertIn("glyph-transition-layout-transaction-v1-style", html)
        self.assertIn("white-space:normal!important", html)
        self.assertIn("text-overflow:clip!important", html)
        self.assertIn("overflow-wrap:anywhere!important", html)
        self.assertNotIn("ANGLE_STEPS=360", html)
        self.assertNotIn("MAX_SEARCH_ITERATIONS=32", html)


if __name__ == "__main__":
    unittest.main()

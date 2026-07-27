from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_label_readability import (
    enhance_transition_label_readability_html,
)


class TransitionLabelReadabilityTests(unittest.TestCase):
    def test_enhancer_forbids_visual_truncation(self) -> None:
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

    def test_prepared_app_installs_readability_layer_last(self) -> None:
        prepare_diagram_app()
        html = diagram_app.DIAGRAM_HTML
        readability = html.index("glyph-transition-label-readability-v1-style")
        collision = html.index("glyph-transition-io-collision-solver-v1-style")
        clusters = html.index("glyph-transition-io-clusters-v1-style")
        self.assertGreater(readability, collision)
        self.assertGreater(readability, clusters)
        self.assertIn("window.glyphTransitionLabelReadability", html)


if __name__ == "__main__":
    unittest.main()

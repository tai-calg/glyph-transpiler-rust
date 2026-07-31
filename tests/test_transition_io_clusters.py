from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_io_clusters import enhance_transition_io_clusters_html


class TransitionIoClusterTests(unittest.TestCase):
    def test_enhancer_renders_one_arrow_label_per_transition(self) -> None:
        html = enhance_transition_io_clusters_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-io-clusters-v1-script", html)
        self.assertIn("transition-io-cluster", html)
        self.assertIn('data-io-kind="io"', html)
        self.assertIn('guard?` [${guard}]`', html)
        self.assertIn('action?` ➞ ${action}`', html)
        self.assertIn('return"otherwise"', html)
        self.assertNotIn('return both("自動","automatic")', html)
        self.assertNotIn('action?` / ${action}`', html)
        self.assertNotIn('data-io-kind="input"', html)
        self.assertNotIn('data-io-kind="output"', html)
        self.assertNotIn('data-io-kind="guard"', html)
        self.assertNotIn("failureOf(transition)", html)
        self.assertNotIn("||text(transition?.target_state)", html)
        self.assertIn("MAX_DISTANCE=96", html)
        self.assertIn("glyph.diagram.transition-io.v1:", html)
        self.assertIn("glyph-transition-io-clusters-ready", html)
        self.assertNotIn("label.textContent=id", html)

    def test_cluster_layer_reads_positions_but_does_not_own_interaction_or_persistence(self) -> None:
        html = enhance_transition_io_clusters_html(DIAGRAM_HTML)
        self.assertIn("localStorage.getItem(storageKey(data))", html)
        self.assertIn('cluster.dataset.interactionOwner="glyph-transition-layout-interaction-adapter-v4"', html)
        self.assertNotIn("localStorage.setItem(storageKey(data)", html)
        self.assertNotIn('cluster.addEventListener("pointerdown"', html)
        self.assertNotIn('cluster.addEventListener("pointermove"', html)
        self.assertNotIn('cluster.addEventListener("pointerup"', html)
        self.assertNotIn("writeSaved(data,saved)", html)

    def test_prepared_diagram_app_contains_transition_io_layer(self) -> None:
        prepare_diagram_app()
        self.assertIn(
            "glyph-transition-io-clusters-v1-script",
            diagram_app.DIAGRAM_HTML,
        )
        self.assertIn("window.glyphTransitionIoClusters", diagram_app.DIAGRAM_HTML)


if __name__ == "__main__":
    unittest.main()

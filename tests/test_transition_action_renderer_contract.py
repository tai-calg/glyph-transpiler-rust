from __future__ import annotations

import unittest

from glyph.transition_io_clusters import enhance_transition_io_clusters_html


class TransitionActionRendererContractTests(unittest.TestCase):
    def test_target_state_is_never_used_as_action_fallback(self) -> None:
        rendered = enhance_transition_io_clusters_html("<html><head></head><body></body></html>")
        self.assertIn("function actionOf(transition)", rendered)
        self.assertNotIn("function outputOf(transition)", rendered)
        self.assertNotIn("||text(transition?.target_state)", rendered)
        self.assertNotIn("||text(transition?.target?.state)", rendered)
        self.assertIn("action=actionOf(transition),value=ioOf(transition)", rendered)
        self.assertIn("cluster.dataset.actionValue=action", rendered)
        self.assertIn("cluster.dataset.outputValue=action", rendered)


if __name__ == "__main__":
    unittest.main()

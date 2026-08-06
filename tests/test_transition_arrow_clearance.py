import unittest

from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_arrow_clearance import enhance_transition_arrow_clearance_html


class TransitionArrowClearanceTest(unittest.TestCase):
    def test_uses_rendered_rounded_node_geometry(self) -> None:
        html = enhance_transition_arrow_clearance_html(
            '<html><head></head><body><div id="view"></div></body></html>'
        )

        for required in (
            "NODE_GAP=6",
            "MARKER_SIZE=12",
            "function cornerRadius(",
            "function boundaryDistance(",
            "function ordinaryPath(",
            "function selfLoopPath(",
            "function installRerouteGuard(",
            'marker.setAttribute("refX","10")',
            'marker.setAttribute("markerUnits","userSpaceOnUse")',
            "transitionArrowClearanceMin",
            "glyph-transition-arrow-clearance-ready",
        ):
            self.assertIn(required, html)

        for forbidden in (
            "setInterval(",
            "MutationObserver(",
        ):
            self.assertNotIn(forbidden, html)

    def test_is_installed_after_workspace_geometry(self) -> None:
        prepare_diagram_app()

        from glyph import diagram_app

        html = diagram_app.DIAGRAM_HTML
        workspace = html.index("glyph-state-diagram-workspace-v2-script")
        clearance = html.index("glyph-transition-arrow-clearance-v1-script")
        clusters = html.index("glyph-transition-io-clusters-v1-script")

        self.assertLess(workspace, clearance)
        self.assertLess(clearance, clusters)


if __name__ == "__main__":
    unittest.main()

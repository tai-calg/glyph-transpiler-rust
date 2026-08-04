from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_arrow_clearance import enhance_transition_arrow_clearance_html


def test_transition_arrow_clearance_uses_rendered_rounded_node_geometry() -> None:
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
        'marker.setAttribute("refX","10")',
        'marker.setAttribute("markerUnits","userSpaceOnUse")',
        "transitionArrowClearanceMin",
        "glyph-transition-arrow-clearance-ready",
    ):
        assert required in html

    for forbidden in (
        "setInterval(",
        "MutationObserver(",
    ):
        assert forbidden not in html


def test_transition_arrow_clearance_is_installed_after_workspace_geometry() -> None:
    prepare_diagram_app()

    from glyph import diagram_app

    html = diagram_app.DIAGRAM_HTML
    workspace = html.index("glyph-state-diagram-workspace-v2-script")
    clearance = html.index("glyph-transition-arrow-clearance-v1-script")
    clusters = html.index("glyph-transition-io-clusters-v1-script")

    assert workspace < clearance < clusters

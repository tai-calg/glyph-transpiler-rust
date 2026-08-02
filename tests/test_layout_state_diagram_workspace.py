from glyph.readable_diagram_app import prepare_diagram_app
from glyph.state_diagram_workspace import enhance_state_diagram_workspace_html


def test_workspace_adapts_density_and_routes_initial_marker_around_obstacles() -> None:
    html = enhance_state_diagram_workspace_html(
        '<html><head></head><body><div id="view"></div></body></html>'
    )

    for required in (
        "MIN_WIDTH=1600",
        "MIN_HEIGHT=960",
        "function adaptiveLayoutMetrics(",
        "stateDiagramWorkspaceContentWidth",
        "stateDiagramWorkspaceSpreadX",
        "stateDiagramWorkspaceAdaptive",
        "complexity-2.4)*.46",
        "complexity-2.8)*.24",
        "function initialPlacementCandidates(",
        "function segmentHitsRect(",
        "function updateInitialTransition(",
        'initialRouteCertificate:best.collisionCount===0?"ordinary-obstacle-free":"ordinary-degraded"',
        "initialRouteCollisionCount",
        "INITIAL_NODE_CLEARANCE=18",
        "INITIAL_LABEL_CLEARANCE=12",
        "window.glyphTransitionIoClusters?.reroute?.(stage)",
        "stateDiagramWorkspaceOriginReady",
        "stateDiagramWorkspaceViewportReady",
        "version:3",
    ):
        assert required in html

    assert (
        "window.glyphTransitionIoClusters?.reroute?.(stage);\n"
        "  updateInitialTransition(stage,machine,paths,nodes);"
    ) in html

    for forbidden in (
        "setInterval(",
        "findBudgeted(",
        'transitionPublicationReady="false"',
    ):
        assert forbidden not in html


def test_workspace_is_installed_in_the_normal_application() -> None:
    prepare_diagram_app()

    from glyph import diagram_app

    html = diagram_app.DIAGRAM_HTML
    viewport = html.index("glyph-diagram-canvas-viewport-v1-script")
    workspace = html.index("glyph-state-diagram-workspace-v2-script")
    node_adapter = html.index("glyph-transition-node-position-adapter-v1-script")

    assert viewport < workspace < node_adapter
    assert "glyph-initial-transition-routing-v2-script" not in html
    assert "glyph-state-diagram-workspace-v2-style" in html

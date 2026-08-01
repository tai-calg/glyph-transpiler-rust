from glyph.readable_diagram_app import prepare_diagram_app
from glyph.state_diagram_workspace import enhance_state_diagram_workspace_html


def test_workspace_restores_initial_transition_details_and_editing_area() -> None:
    html = enhance_state_diagram_workspace_html(
        '<html><head></head><body><div id="view"></div></body></html>'
    )

    for required in (
        "MIN_WIDTH=1600",
        "MIN_HEIGHT=960",
        "function updateInitialTransition(",
        "function updateTransitionGeometry(",
        "function renderTransitionIndex(",
        'class="transition-detail"',
        'panel.className="transition-index"',
        'attributeFilter:["style"]',
        'stage.dataset.initialRouteCertificate="ordinary-follow"',
        'window.glyphTransitionIoClusters?.reroute?.(stage)',
        "stateDiagramWorkspaceOriginReady",
        "stateDiagramWorkspaceViewportReady",
    ):
        assert required in html

    for forbidden in (
        "setInterval(",
        "candidateRoutes(",
        "findBudgeted(",
        "transitionPublicationReady=\"false\"",
    ):
        assert forbidden not in html


def test_workspace_is_installed_in_the_normal_application() -> None:
    prepare_diagram_app()

    from glyph import diagram_app

    html = diagram_app.DIAGRAM_HTML
    viewport = html.index("glyph-diagram-canvas-viewport-v1-script")
    workspace = html.index("glyph-state-diagram-workspace-v1-script")
    node_adapter = html.index("glyph-transition-node-position-adapter-v1-script")

    assert viewport < workspace < node_adapter
    assert "glyph-initial-transition-routing-v2-script" not in html
    assert "glyph-state-diagram-workspace-v1-style" in html

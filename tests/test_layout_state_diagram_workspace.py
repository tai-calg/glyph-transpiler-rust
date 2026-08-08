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
        "complexity-2.4)*.72",
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
        "version:4",
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


def test_node_drag_updates_only_incident_geometry_until_pointer_release() -> None:
    html = enhance_state_diagram_workspace_html(
        '<html><head></head><body><div id="view"></div></body></html>'
    )

    for required in (
        "DRAG_FRAME_BUDGET_MS=8",
        "const incidentIndexCache=new WeakMap()",
        "function incidentIndexes(stage,machine)",
        "function updateIncidentTransitionGeometry(stage,machine,node)",
        "const movedName=stateName(node),indexes=incidentIndexes(stage,machine).get(movedName)||[]",
        "function fastInitialPath(dot,target)",
        'if(movedName===String(machine.initial_state||""))',
        "stateDiagramWorkspaceIncidentGeometryPasses",
        "stateDiagramWorkspaceFullGeometryPasses",
        "stateDiagramWorkspaceDragBudgetExceeded",
        'document.addEventListener("pointermove",event=>{const node=event.target?.closest?.(".state-node");if(node)scheduleIncident(node)},true)',
        'setTimeout(()=>schedule("node-drag-complete"),20)',
        "updateNodeGeometry:updateIncidentTransitionGeometry",
    ):
        assert required in html

    assert '.observe(view,{childList:true,subtree:true});' in html
    assert 'attributeFilter:["style"]' not in html
    assert "attributes:true" not in html


def test_workspace_is_installed_in_the_normal_application() -> None:
    prepare_diagram_app()

    from glyph import diagram_app

    html = diagram_app.DIAGRAM_HTML
    viewport = html.index("glyph-diagram-canvas-viewport-v1-script")
    workspace = html.index("glyph-state-diagram-workspace-v2-script")
    node_adapter = html.index("glyph-transition-node-position-adapter-v1-script")
    clusters = html.index("glyph-transition-io-clusters-v1-script")

    assert viewport < workspace < node_adapter < clusters
    assert "glyph-initial-transition-routing-v2-script" not in html
    assert "glyph-state-diagram-workspace-v2-style" in html

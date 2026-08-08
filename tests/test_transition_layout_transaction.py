from glyph.diagram_canvas_viewport import enhance_diagram_canvas_viewport_html
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_io_clusters import enhance_transition_io_clusters_html
from glyph.transition_layout_interaction_adapter import (
    enhance_transition_layout_interaction_adapter_html,
)
from glyph.transition_layout_transaction import (
    enhance_transition_layout_transaction_html,
)
from glyph.transition_layout_transaction_bootstrap import (
    enhance_transition_layout_transaction_bootstrap_html,
)
from glyph.transition_node_position_adapter import (
    enhance_transition_node_position_adapter_html,
)


def test_bootstrap_does_not_monkey_patch_browser_scheduling() -> None:
    html = enhance_transition_layout_transaction_bootstrap_html(
        "<html><head></head><body></body></html>"
    )

    assert "ownsScheduling:true" in html
    assert 'protocol:"ordinary-layout-v1"' in html
    assert "EventTarget.prototype.addEventListener" not in html
    assert "window.setTimeout=function" not in html
    assert "window.MutationObserver=" not in html


def test_transaction_is_strictly_bounded_and_preserves_base_geometry() -> None:
    html = enhance_transition_layout_transaction_html(
        "<html><head></head><body></body></html>"
    )

    for required in (
        "TRANSACTION_DEADLINE_MS=48",
        "FRAME_SLICE_BUDGET_MS=8",
        "MAX_FRAME_BUDGET=2",
        "MAX_RETRIES=0",
        "maxRetries:MAX_RETRIES",
        'stage.dataset.transitionLayoutProfile="ordinary"',
        'stage.dataset.transitionLayoutMode="base"',
        'stage.dataset.transitionDenseCanvas="disabled"',
        'stage.dataset.transitionPublicationReady="true"',
        "requestAndWait",
        'geometryOwner:"base-renderer"',
        'cancel("state-tab-deactivated")',
        "function ownersReady(stage)",
        "function requestOwners(stage,reason)",
        "window.glyphStateDiagramWorkspace?.schedule?.(`transaction:${reason}`)",
        "transitionLayoutOwnerDispatchMaxMs",
        "transitionLayoutFrameSliceBudgetExceeded",
        "version:9",
    ):
        assert required in html

    for removed in (
        'fetch("/api/state"',
        "candidateRoutes",
        "positionLabels(",
        "standardCanvas(",
        "stateCurve(",
        "ensureClusters(",
        "__glyphRenderStateFailure",
        "State diagram certification failed",
        'stage.dataset.transitionPublicationReady="false"',
        "window.glyphStateDiagramWorkspace?.prepare?.(stage)",
        "window.glyphTransitionIoClusters?.reroute?.(stage)",
    ):
        assert removed not in html


def test_superseded_transaction_waiters_resolve_on_later_generation() -> None:
    html = enhance_transition_layout_transaction_html(
        "<html><head></head><body></body></html>"
    )

    assert "function settleWaiters(result)" in html
    assert "completedGeneration>=waiter.token" in html
    assert "waiters.push({token,resolve})" in html
    assert "settleWaiters(result)" in html
    assert "get waiterCount(){return waiters.length}" in html
    assert 'schedule(reason,0);\n  return lastPromise;' not in html


def test_io_clusters_use_bounded_ordinary_placement() -> None:
    html = enhance_transition_io_clusters_html(
        "<html><head></head><body><div id=\"view\"></div></body></html>"
    )

    for required in (
        "RENDER_BUDGET_MS=16",
        "STATE_REQUEST_TIMEOUT_MS=48",
        "AUTO_OFFSET=18",
        "LANE_GAP=34",
        "COLLISION_BUDGET_MS=10",
        "COLLISION_RINGS=[0,16,32,48,64,80,96]",
        "COLLISION_ANGLES=24",
        "function ordinaryPath(",
        "directionalOffset=48",
        "laneGap=28",
        "ordinaryPath(source,target,source===target,lanes[index],stage)",
        "function reroute(",
        "function pairRanks(",
        "function placeCluster(",
        "function repairCollisions(stage,entries)",
        'profile:"ordinary"',
        "transitionIoRenderBudgetExceeded",
        "transitionIoCollisionBudgetMs",
        '.observe(view,{childList:true})',
    ):
        assert required in html

    for removed in (
        "for(let attempt=0;attempt<100",
        "setInterval(",
        "{childList:true,subtree:true}",
        "nano-io",
        "micro-io",
        "compact-io",
    ):
        assert removed not in html


def test_manual_labels_restore_against_the_saved_arrow_anchor() -> None:
    cluster_html = enhance_transition_io_clusters_html(
        "<html><head></head><body></body></html>"
    )
    interaction_html = enhance_transition_layout_interaction_adapter_html(
        "<html><head></head><body></body></html>"
    )

    assert "finite(record?.dx)&&finite(record?.dy)" in cluster_html
    assert "x:anchor.x+record.dx,y:anchor.y+record.dy" in cluster_html
    assert "cluster.dataset.anchorFraction=String(anchor.fraction)" in cluster_html
    assert "cluster.dataset.ioDistance=String(Math.hypot(point.x-anchor.x,point.y-anchor.y))" in cluster_html
    assert "const MAX_DISTANCE=96" in cluster_html

    assert "anchorFraction:clamp(num(cluster.dataset.anchorFraction)||.5,.18,.82)" in interaction_html
    assert "anchorFraction:record.anchorFraction" in interaction_html
    assert "record.cluster.dataset.anchorFraction=String(record.anchorFraction)" in interaction_html


def test_interaction_adapters_persist_only_real_drags() -> None:
    label_html = enhance_transition_layout_interaction_adapter_html(
        "<html><head></head><body></body></html>"
    )
    node_html = enhance_transition_node_position_adapter_html(
        "<html><head></head><body></body></html>"
    )

    for html in (label_html, node_html):
        assert "DRAG_THRESHOLD=3" in html
        assert 'document.addEventListener("pointercancel"' in html
        assert "AbortController" in html
        assert 'eventName of["pagehide","beforeunload"]' in html

    assert "pointerDistance(active,event)<DRAG_THRESHOLD" in label_html
    assert "active.finalPoint=point" in label_html
    assert "if(!record.dragged||!record.finalPoint)return" in label_html
    assert "setPointerCapture?.(event.pointerId)" in label_html
    assert "releasePointerCapture?.(event.pointerId)" in label_html
    assert "pointerDistance(active,event)<DRAG_THRESHOLD" in node_html
    assert "if(!record.moved)" in node_html
    assert "restorePositionStorageState(record.storageBefore)" in node_html


def test_viewport_is_source_scoped_and_initially_fits_completed_layout() -> None:
    html = enhance_diagram_canvas_viewport_html(
        "<html><head></head><body></body></html>"
    )

    assert "dataset.diagramDigest" in html
    assert "glyph-transition-layout-transaction-ready" in html
    assert "fitInitial" in html
    assert 'saveScale(1,"reset")' in html
    assert 'mode==="fit"' in html
    assert "version:2" in html


def test_diagram_app_uses_only_the_bounded_ordinary_layout_stack() -> None:
    prepare_diagram_app()

    from glyph import diagram_app

    html = diagram_app.DIAGRAM_HTML
    node_adapter = html.index("glyph-transition-node-position-adapter-v1-script")
    clusters = html.index("glyph-transition-io-clusters-v1-script")
    transaction = html.index("glyph-transition-layout-transaction-v1-script")
    interaction = html.index("glyph-transition-layout-interaction-adapter-v1-script")

    assert node_adapter < clusters < transaction < interaction
    assert "glyph-transition-label-layout-v1-script" not in html
    assert "glyph-uml-transition-semantics-v1-script" not in html
    assert "glyph-initial-transition-routing-v2-script" not in html
    assert "glyph-layout-publication-certificate-v1-script" not in html
    assert "glyph-diagram-fit-stability-v1-script" not in html
    assert "glyph-transition-layout-transaction-bootstrap-v1-script" not in html
    assert "State diagram certification failed" not in html

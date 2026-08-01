from glyph.diagram_canvas_viewport import enhance_diagram_canvas_viewport_html
from glyph.initial_transition_dependency_bridge import (
    enhance_initial_transition_dependency_bridge_html,
)
from glyph.readable_diagram_app import prepare_diagram_app
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


def test_bootstrap_precedes_transaction_owner() -> None:
    html = enhance_transition_layout_transaction_html(
        enhance_transition_layout_transaction_bootstrap_html(
            "<html><head></head><body></body></html>"
        )
    )

    assert html.index("glyph-transition-layout-transaction-bootstrap-v1-script") < html.index(
        "glyph-transition-layout-transaction-v1-script"
    )
    assert "ownsScheduling:false" in html
    assert "control.ownsScheduling=true" in html


def test_transaction_is_time_bounded_and_uses_ordinary_layout() -> None:
    html = enhance_transition_layout_transaction_html(
        "<html><head></head><body></body></html>"
    )

    for required in (
        "TOTAL_BUDGET_MS=120",
        "PREREQUISITE_BUDGET_MS=180",
        "CLUSTER_BUDGET_MS=80",
        "standardCanvas(stage)",
        "stateCurve(source,target,same,lane,laneCount)",
        "reroute(stage,machine)",
        "ensureClusters(stage,machine,token,deadline)",
        "positionLabels(stage,data,machine)",
        "const result=audit(stage)",
        'stage.dataset.transitionLayoutProfile="interactive-fast"',
        'stage.dataset.transitionLayoutState="ready"',
        'stage.dataset.transitionPublicationReady="false"',
        'stage.dataset.transitionDenseCanvas="disabled"',
        'cancel("state-tab-deactivated")',
    ):
        assert required in html

    for removed in (
        "SEARCH_STEPS",
        "SEARCH_BUDGET_MS",
        "solveEntries",
        "greedyEntries",
        "arrangeInitialDenseNodes",
        "candidatePoints",
        "layout-assignment-unsatisfied",
    ):
        assert removed not in html

    assert "visibility:visible!important" in html
    assert "pointer-events:auto!important" in html
    assert "window.glyphDiagramViewport?.fitInitial?.()" in html
    assert "await nextFrame()" in html
    assert "new MutationObserver(synchronizeStage)" in html


def test_manual_labels_restore_against_the_saved_arrow_anchor() -> None:
    transaction_html = enhance_transition_layout_transaction_html(
        "<html><head></head><body></body></html>"
    )
    interaction_html = enhance_transition_layout_interaction_adapter_html(
        "<html><head></head><body></body></html>"
    )

    assert "finite(record?.anchorFraction)" in transaction_html
    assert "anchorFor(path,fraction)" in transaction_html
    assert "x:anchor.x+record.dx,y:anchor.y+record.dy" in transaction_html
    assert "cluster.dataset.anchorFraction=String(anchor.fraction)" in transaction_html
    assert "cluster.dataset.ioDistance=String(Math.hypot(point.x-anchor.x,point.y-anchor.y))" in transaction_html
    assert "const MAX_DISTANCE=96" in transaction_html

    assert "anchorFraction:clamp(num(cluster.dataset.anchorFraction)||.5,.18,.82)" in interaction_html
    assert "anchorFraction:record.anchorFraction" in interaction_html
    assert "record.cluster.dataset.anchorFraction=String(record.anchorFraction)" in interaction_html


def test_certified_route_owner_requests_publication_directly() -> None:
    html = enhance_initial_transition_dependency_bridge_html(
        "<html><head></head><body></body></html>"
    )

    publication_request = (
        'window.glyphLayoutPublicationCertificate?.schedule?.(\n'
        '      "glyph-initial-transition-route-ready",\n'
        "      0,\n"
        "    );"
    )
    assert publication_request in html
    assert html.index(publication_request) < html.index(
        'document.dispatchEvent(new CustomEvent("glyph-initial-transition-route-ready"'
    )
    assert 'stage.dataset.initialRouteSettleState = "stable"' in html
    assert "layoutGeneration: generation" in html


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
    assert 'publicationGuard()?.invalidate?.(active.stage,"manual-label-drag")' in label_html
    assert "nearestCertifiablePoint(record,requested)" in label_html
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


def test_diagram_app_installs_lightweight_transaction_layers() -> None:
    prepare_diagram_app()

    from glyph import diagram_app

    html = diagram_app.DIAGRAM_HTML
    bootstrap = html.index("glyph-transition-layout-transaction-bootstrap-v1-script")
    clusters = html.index("glyph-transition-io-clusters-v1-script")
    transaction = html.index("glyph-transition-layout-transaction-v1-script")
    viewport = html.index("glyph-diagram-canvas-viewport-v1-script")

    assert bootstrap < clusters < transaction
    assert viewport < transaction
    assert "glyph-transition-dense-canvas-dimensions-v1-script" not in html
    assert "glyph-transition-io-collision-solver-v1-script" not in html
    assert "glyph-transition-label-readability-v1-script" not in html

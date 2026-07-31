from glyph.diagram_canvas_viewport import enhance_diagram_canvas_viewport_html
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
    assert "ownsScheduling=false" in html
    assert "control.ownsScheduling=true" in html


def test_transaction_contains_publication_grade_layout_phases() -> None:
    html = enhance_transition_layout_transaction_html(
        "<html><head></head><body></body></html>"
    )

    for required in (
        "waitForPrerequisites(token)",
        "waitForFonts(token)",
        "ensureCanvas(stage",
        "arrangeInitialDenseNodes(stage",
        "reroute(stage,machine)",
        "ensureClusters(stage,machine,token)",
        "formatLabels(stage,strategy.maxLineWidth)",
        "layoutEntries(stage,data,machine)",
        "greedyEntries(entries)",
        "solveEntries(entries,token)",
        "applyAssignment(stage,data,entries,solver.assignment)",
        "const result=audit(stage)",
        'stage.dataset.transitionLayoutState="ready"',
        'stage.dataset.transitionPublicationReady="true"',
    ):
        assert required in html

    assert "SEARCH_BUDGET_MS=180" in html
    assert "SEARCH_STEPS=220000" in html
    assert "splitByWidth" in html
    assert "renderedCanonical" in html
    assert "feasiblePoint" in html
    assert "ResizeObserver" in html
    assert "AbortController" in html
    assert "transitionLayoutFailureCode" in html
    assert "transition-count:" in html
    assert "missing-accessible-label" in html
    assert "writeStored(labelStorageKey(data),saved)" in html
    assert "window.glyphDiagramViewport?.fitInitial?.()" in html


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

    assert "pointerDistance<DRAG_THRESHOLD&&visualDistance<1" in label_html
    assert "Math.hypot(next.x-anchor.x,next.y-anchor.y)>MAX_DISTANCE+.25" in label_html
    assert "pointerDistance<DRAG_THRESHOLD&&visualDistance<1" in node_html


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


def test_diagram_app_installs_transaction_layers() -> None:
    prepare_diagram_app()

    from glyph import diagram_app

    html = diagram_app.DIAGRAM_HTML
    bootstrap = html.index("glyph-transition-layout-transaction-bootstrap-v1-script")
    clusters = html.index("glyph-transition-io-clusters-v1-script")
    transaction = html.index("glyph-transition-layout-transaction-v1-script")
    viewport = html.index("glyph-diagram-canvas-viewport-v1-script")

    assert bootstrap < clusters < transaction
    assert viewport < transaction

from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_layout_transaction import (
    enhance_transition_layout_transaction_html,
)
from glyph.transition_layout_transaction_bootstrap import (
    enhance_transition_layout_transaction_bootstrap_html,
)


def test_bootstrap_precedes_transaction_owner() -> None:
    html = enhance_transition_layout_transaction_html(
        enhance_transition_layout_transaction_bootstrap_html("<html><head></head><body></body></html>")
    )

    assert html.index("glyph-transition-layout-transaction-bootstrap-v1-script") < html.index(
        "glyph-transition-layout-transaction-v1-script"
    )
    assert "ownsScheduling=false" in html
    assert "control.ownsScheduling=true" in html


def test_transaction_contains_required_layout_phases() -> None:
    html = enhance_transition_layout_transaction_html("<html><head></head><body></body></html>")

    for required in (
        "ensureCanvas(stage",
        "arrangeInitialDenseNodes(stage",
        "reroute(stage,machine)",
        "ensureClusters(stage,machine,token)",
        "formatLabels(stage)",
        "layoutEntries(stage,data)",
        "applyAssignment(stage,data,entries,assignment)",
        "const result=audit(stage)",
        'stage.dataset.transitionLayoutState="ready"',
    ):
        assert required in html

    assert "requestedGeneration" in html
    assert "completedGeneration" in html
    assert "writeStored(labelStorageKey(data),saved)" in html


def test_diagram_app_installs_transaction_layers() -> None:
    prepare_diagram_app()

    from glyph import diagram_app

    html = diagram_app.DIAGRAM_HTML
    bootstrap = html.index("glyph-transition-layout-transaction-bootstrap-v1-script")
    clusters = html.index("glyph-transition-io-clusters-v1-script")
    transaction = html.index("glyph-transition-layout-transaction-v1-script")

    assert bootstrap < clusters < transaction

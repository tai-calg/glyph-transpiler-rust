from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_io_canonicalizer import enhance_transition_io_canonicalizer_html


def test_canonicalizer_removes_split_input_and_output_nodes() -> None:
    html = enhance_transition_io_canonicalizer_html(
        '<html><head></head><body><div id="view"></div></body></html>'
    )

    assert 'data-io-kind="io"' in html
    assert 'data-io-kind="input"' in html
    assert 'data-io-kind="output"' in html
    assert "function canonical(cluster)" in html
    assert "function normalize(cluster)" in html
    assert 'stage.dataset.transitionIoCanonical="true"' in html
    assert 'glyph-transition-io-clusters-ready' in html
    assert "setInterval(" not in html


def test_canonicalizer_runs_after_cluster_renderer() -> None:
    prepare_diagram_app()

    from glyph import diagram_app

    html = diagram_app.DIAGRAM_HTML
    clusters = html.index("glyph-transition-io-clusters-v1-script")
    canonicalizer = html.index("glyph-transition-io-canonicalizer-v1-script")
    transaction = html.index("glyph-transition-layout-transaction-v1-script")

    assert clusters < canonicalizer < transaction

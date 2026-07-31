from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from glyph.initial_transition_layout import enhance_initial_transition_html
from glyph.layout_publication_certificate import enhance_layout_publication_certificate_html
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_layout_transaction_bootstrap import (
    enhance_transition_layout_transaction_bootstrap_html,
)


def test_protocol_enforces_one_way_generation_order() -> None:
    html = enhance_transition_layout_transaction_bootstrap_html(
        "<html><head></head><body></body></html>"
    )

    assert 'protocol:"layout-generation-v1"' in html
    assert "transactionDownstreamEvents" in html
    assert "transactionReadinessEvents" in html
    assert '"glyph-transition-enabling-cases-ready"' in html
    assert '"glyph-transition-io-clusters-ready"' in html
    assert '"glyph-uml-transition-ready"' in html
    assert "publicationIndependentEvents" in html
    assert 'event?.detail?.stable!==true' in html
    assert "initialRouteLayoutGeneration" in html
    assert 'initialRouteCertificate="pending"' in html
    assert 'layoutCertificateRequestState="invalidated"' in html
    assert 'reason==="state-tab-activated"' in html
    assert '["pending","ready"].includes(stage.dataset.transitionLayoutState)' in html


def test_bootstrap_does_not_mask_generation_consumer_enhancements() -> None:
    base = "<html><head></head><body></body></html>"
    bootstrapped = enhance_transition_layout_transaction_bootstrap_html(base)
    with_router = enhance_initial_transition_html(bootstrapped)
    enhanced = enhance_layout_publication_certificate_html(with_router)

    assert "glyph-initial-transition-routing-v2" not in bootstrapped
    assert "glyph-layout-publication-certificate-v1" not in bootstrapped
    assert '<script id="glyph-initial-transition-routing-v2-script">' in enhanced
    assert '<script id="glyph-layout-publication-certificate-v1-script">' in enhanced


def test_initial_router_is_owned_by_the_completed_transaction_generation() -> None:
    html = enhance_transition_layout_transaction_bootstrap_html(
        "<html><head></head><body></body></html>"
    )

    assert 'if(ownerId===initialRouterScript)' in html
    assert 'window.glyphInitialTransitionRouter?.schedule?.("transaction-generation-ready",0)' in html
    assert 'initialRouteProtocolState="waiting-dom"' in html
    assert 'initialRouteProtocolState="router-stalled"' in html
    assert "api.completedGeneration<routerGeneration" in html


def test_synthetic_editor_prerequisite_is_released_before_publication() -> None:
    html = enhance_transition_layout_transaction_bootstrap_html(
        "<html><head></head><body></body></html>"
    )

    assert 'transitionEditorPrerequisite="synthetic"' in html
    assert "releaseTransactionPrerequisite(stage)" in html
    assert '"glyph-layout-publication-certificate-ready"' in html
    assert '"glyph-initial-transition-ready"' in html


def test_protocol_bootstrap_precedes_all_generation_consumers() -> None:
    prepare_diagram_app()

    from glyph import diagram_app

    html = diagram_app.DIAGRAM_HTML
    bootstrap = html.index("glyph-transition-layout-transaction-bootstrap-v1-script")
    initial_router = html.index("glyph-initial-transition-routing-v2-script")
    transaction = html.index("glyph-transition-layout-transaction-v1-script")
    publication = html.index("glyph-layout-publication-certificate-v1-script")

    assert bootstrap < initial_router < transaction < publication


def test_injected_protocol_javascript_is_syntactically_valid() -> None:
    if not shutil.which("node"):
        return
    html = enhance_transition_layout_transaction_bootstrap_html(
        "<html><head></head><body></body></html>"
    )
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "layout-generation-protocol.js"
        script.write_text("\n".join(scripts), encoding="utf-8")
        result = subprocess.run(
            ["node", "--check", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 0, result.stderr

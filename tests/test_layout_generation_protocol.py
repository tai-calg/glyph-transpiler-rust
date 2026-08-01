from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_layout_transaction_bootstrap import (
    enhance_transition_layout_transaction_bootstrap_html,
)


def test_bootstrap_delegates_to_the_bounded_ordinary_transaction() -> None:
    html = enhance_transition_layout_transaction_bootstrap_html(
        "<html><head></head><body></body></html>"
    )

    assert "ownsScheduling:true" in html
    assert 'protocol:"ordinary-layout-v1"' in html
    assert "glyphTransitionLayoutTransaction?.schedule?.(reason,0)" in html
    assert "layout-generation-v1" not in html
    assert "initialRouteProtocolState" not in html
    assert "layoutCertificateRequestState" not in html


def test_bootstrap_does_not_monkey_patch_browser_apis() -> None:
    html = enhance_transition_layout_transaction_bootstrap_html(
        "<html><head></head><body></body></html>"
    )

    assert "EventTarget.prototype.addEventListener" not in html
    assert "window.setTimeout=function" not in html
    assert "window.MutationObserver=" not in html
    assert "document.dispatchEvent=function" not in html


def test_interactive_app_uses_the_transaction_without_legacy_protocol_layers() -> None:
    prepare_diagram_app()

    from glyph import diagram_app

    html = diagram_app.DIAGRAM_HTML
    assert "glyph-transition-layout-transaction-v1-script" in html
    assert "glyph-transition-layout-transaction-bootstrap-v1-script" not in html
    assert "glyph-initial-transition-routing-v2-script" not in html
    assert "glyph-layout-publication-certificate-v1-script" not in html
    assert "State diagram certification failed" not in html


def test_injected_bootstrap_javascript_is_syntactically_valid() -> None:
    if not shutil.which("node"):
        return
    html = enhance_transition_layout_transaction_bootstrap_html(
        "<html><head></head><body></body></html>"
    )
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "ordinary-layout-bootstrap.js"
        script.write_text("\n".join(scripts), encoding="utf-8")
        result = subprocess.run(
            ["node", "--check", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 0, result.stderr

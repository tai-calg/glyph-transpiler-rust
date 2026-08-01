from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from glyph.manual_layout_semantic_guard import (
    enhance_manual_layout_semantic_guard_html,
)
from glyph.readable_diagram_app import _presentation_pipeline


def test_guard_snapshots_and_restores_semantic_dataset_fields() -> None:
    html = enhance_manual_layout_semantic_guard_html(
        "<html><head></head><body></body></html>"
    )

    for key in (
        "ioValue",
        "inputValue",
        "guardValue",
        "actionValue",
        "outputValue",
        "emittedOutputValue",
    ):
        assert f'"{key}"' in html
    assert "armManualRun()" in html
    assert 'stage?.dataset.transitionLayoutReason === "manual-run"' in html
    assert "restoreSemanticSnapshot(candidate.values)" in html
    assert 'stage.dataset.manualLayoutSemanticGuard = `restored:${restored}`' in html


def test_guard_only_preserves_semantics_and_does_not_own_recertification() -> None:
    html = enhance_manual_layout_semantic_guard_html(
        "<html><head></head><body></body></html>"
    )

    assert "requestPublicationRecertification" not in html
    assert "glyphInitialTransitionRouter" not in html
    assert "glyphLayoutPublicationCertificate" not in html
    assert "ROUTE_WAIT_LIMIT" not in html
    assert "ROUTE_WAIT_DELAY_MS" not in html
    assert 'document.addEventListener("glyph-transition-layout-transaction-ready", install)' in html
    assert "version: 4" in html


def test_guard_is_installed_after_transaction_and_before_interaction() -> None:
    names = [enhancer.__name__ for enhancer in _presentation_pipeline()]

    transaction = names.index("enhance_transition_layout_transaction_html")
    guard = names.index("enhance_manual_layout_semantic_guard_html")
    interaction = names.index("enhance_transition_layout_interaction_adapter_html")

    assert transaction < guard < interaction


def test_guard_injected_javascript_is_syntactically_valid() -> None:
    if not shutil.which("node"):
        return
    html = enhance_manual_layout_semantic_guard_html(
        "<html><head></head><body></body></html>"
    )
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "manual-layout-semantic-guard.js"
        script.write_text("\n".join(scripts), encoding="utf-8")
        result = subprocess.run(
            ["node", "--check", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 0, result.stderr

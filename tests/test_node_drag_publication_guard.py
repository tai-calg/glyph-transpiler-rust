from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from glyph.node_drag_publication_guard import (
    enhance_node_drag_publication_guard_html,
)
from glyph.transition_node_position_adapter import (
    enhance_transition_node_position_adapter_html,
)


def test_guard_exposes_fail_closed_publication_capability() -> None:
    html = enhance_node_drag_publication_guard_html(
        "<html><head></head><body></body></html>"
    )

    assert 'stage.dataset.transitionLayoutState = "pending"' in html
    assert 'stage.dataset.transitionPublicationReady = "false"' in html
    assert 'stage.dataset.transitionIoCollisionSolved = "transaction-pending"' in html
    assert 'stage.dataset.layoutCertificateRequestState = "invalidated"' in html
    assert 'window.glyphTransitionLayoutTransaction?.schedule?.(reason, 0)' in html
    assert 'interactionOwner: "glyph-transition-node-position-adapter-v8"' in html
    assert "ownsPointerEvents: false" in html
    assert "ownsKeyboardEvents: false" in html
    assert "version: 3" in html


def test_guard_does_not_compete_for_interaction_events() -> None:
    html = enhance_node_drag_publication_guard_html(
        "<html><head></head><body></body></html>"
    )

    assert 'document.addEventListener("pointerdown"' not in html
    assert 'document.addEventListener("pointermove"' not in html
    assert 'document.addEventListener("pointerup"' not in html
    assert 'document.addEventListener("pointercancel"' not in html
    assert 'document.addEventListener("keydown"' not in html


def test_node_owner_invokes_guard_after_accepting_the_interaction() -> None:
    html = enhance_transition_node_position_adapter_html(
        "<html><head></head><body></body></html>"
    )

    assert 'invalidatePublication(active,"manual-node-drag")' in html
    assert 'invalidatePublication(record,"manual-node-keyboard")' in html
    assert 'publicationGuard()?.schedule?.("manual-node-cancelled")' in html
    assert "function editingContext(event)" in html
    assert "target?.closest?.(EDITING_SELECTOR)" in html
    assert "focused?.closest?.(EDITING_SELECTOR)" in html
    assert "version:8" in html


def test_guard_javascript_is_syntactically_valid() -> None:
    if not shutil.which("node"):
        return
    html = enhance_node_drag_publication_guard_html(
        "<html><head></head><body></body></html>"
    )
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "node-drag-publication-guard.js"
        script.write_text("\n".join(scripts), encoding="utf-8")
        result = subprocess.run(
            ["node", "--check", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 0, result.stderr

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from glyph.node_drag_publication_guard import (
    enhance_node_drag_publication_guard_html,
)
from glyph.readable_diagram_app import _presentation_pipeline


def test_guard_invalidates_stale_publication_only_after_real_movement() -> None:
    html = enhance_node_drag_publication_guard_html(
        "<html><head></head><body></body></html>"
    )

    assert "DRAG_THRESHOLD = 3" in html
    assert "pointerDistance(active, event) < DRAG_THRESHOLD" in html
    assert 'stage.dataset.transitionLayoutState = "pending"' in html
    assert 'stage.dataset.transitionPublicationReady = "false"' in html
    assert 'stage.dataset.transitionIoCollisionSolved = "transaction-pending"' in html
    assert 'stage.dataset.layoutCertificateRequestState = "invalidated"' in html
    assert 'invalidate(active.stage, "manual-node-drag")' in html
    assert 'invalidate(stage, "manual-node-keyboard")' in html
    assert 'stage.dataset.initialRouteReady = "pending"' not in html
    assert 'stage.dataset.transitionSemanticLinesReady = "pending"' not in html


def test_guard_directly_schedules_every_completed_movement() -> None:
    html = enhance_node_drag_publication_guard_html(
        "<html><head></head><body></body></html>"
    )

    assert 'schedule("manual-node-dragged")' in html
    assert 'schedule("manual-node-cancelled")' in html
    assert 'schedule("manual-node-keyboard")' in html
    assert 'window.glyphTransitionLayoutTransaction?.schedule?.(reason, 0)' in html


def test_guard_precedes_node_position_owner() -> None:
    names = [enhancer.__name__ for enhancer in _presentation_pipeline()]

    guard = names.index("enhance_node_drag_publication_guard_html")
    owner = names.index("enhance_transition_node_position_adapter_html")

    assert guard < owner


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

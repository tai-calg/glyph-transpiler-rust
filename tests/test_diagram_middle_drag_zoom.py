from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from glyph import diagram_app
from glyph.diagram_middle_drag_zoom import enhance_diagram_middle_drag_zoom_html
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.editor_identifier_highlight import enhance_editor_identifier_highlight_html
from glyph.readable_diagram_app import prepare_diagram_app


def test_identifier_highlight_only_overlays_matching_backgrounds() -> None:
    html = enhance_editor_identifier_highlight_html(DIAGRAM_HTML)

    assert ".identifier-highlight-surface" in html
    assert "background:transparent" in html
    assert ".identifier-highlight-layer{" in html
    assert "color:transparent" in html
    assert ".identifier-highlight-layer mark{" in html
    assert "background:rgba(148,163,184,.24)" in html
    assert ".editor-wrap>.editor" in html
    assert ".editor-wrap.identifier-highlight-active>.editor{" not in html
    assert "color:transparent!important" not in html
    assert "background:transparent!important" not in html


def test_middle_button_drag_is_translated_into_anchor_preserving_zoom() -> None:
    html = enhance_diagram_middle_drag_zoom_html(DIAGRAM_HTML)

    for required in (
        'event.button!==1',
        'new WheelEvent("wheel"',
        "ctrlKey:true",
        "clientX:record.anchorX",
        "clientY:record.anchorY",
        "shell.setPointerCapture?.(event.pointerId)",
        "shell.releasePointerCapture?.(record.pointerId)",
        'shell.dataset.middleDragZoomState="dragging"',
        'shell.dataset.middleDragZoomState="idle"',
        "requestAnimationFrame",
        "DRAG_TO_WHEEL=2",
    ):
        assert required in html


def test_prepared_app_installs_middle_drag_zoom_after_viewport() -> None:
    prepare_diagram_app()
    html = diagram_app.DIAGRAM_HTML

    viewport = html.index("glyph-diagram-canvas-viewport-v1-script")
    middle_drag = html.index("glyph-diagram-middle-drag-zoom-v1-script")
    assert viewport < middle_drag
    assert "window.glyphDiagramMiddleDragZoom" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_injected_javascript_is_syntactically_valid() -> None:
    html = enhance_diagram_middle_drag_zoom_html(
        enhance_editor_identifier_highlight_html(DIAGRAM_HTML)
    )
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "diagram-middle-drag-zoom.js"
        script.write_text("\n".join(scripts), encoding="utf-8")
        result = subprocess.run(
            ["node", "--check", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 0, result.stderr

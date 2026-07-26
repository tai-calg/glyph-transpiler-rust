from __future__ import annotations

from pathlib import Path
import unittest

from glyph.diagram_label_editor import enhance_diagram_label_editor_html
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.diagram_workspace_layout import enhance_workspace_layout_html


ROOT = Path(__file__).resolve().parents[1]


class DiagramWorkspaceLayoutTests(unittest.TestCase):
    def test_editor_and_preview_have_independent_scroll_contracts(self) -> None:
        html = enhance_workspace_layout_html(DIAGRAM_HTML)
        self.assertIn("glyph-workspace-layout-v1-style", html)
        self.assertIn("main{flex:1 1 0;height:0", html)
        self.assertIn(".editor{min-height:0;max-height:100%;overflow:auto!important", html)
        self.assertIn(".view-body{flex:1 1 0;min-height:0;overflow:auto!important", html)
        self.assertIn("overscroll-behavior:contain", html)
        self.assertIn(".viewer-head{height:auto!important", html)
        self.assertIn(".diagram-tools{margin-left:auto!important", html)

    def test_labels_are_collision_aware_draggable_and_persistent(self) -> None:
        html = enhance_diagram_label_editor_html(DIAGRAM_HTML)
        self.assertIn("glyph-diagram-label-editor-v1-script", html)
        self.assertIn("glyph.diagram.label-positions.v1:", html)
        self.assertIn("label.setPointerCapture", html)
        self.assertIn("dragging-label", html)
        self.assertIn("occupied.some(item=>intersects", html)
        self.assertIn("placed.some(item=>intersects", html)
        self.assertIn("NODE_SELECTOR", html)
        self.assertIn("dblclick", html)

    def test_tauri_parent_does_not_create_a_second_page_scroll_area(self) -> None:
        css = (ROOT / "desktop" / "ui" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("grid-template-rows: auto minmax(0, 1fr)", css)
        self.assertIn("height: 100dvh", css)
        self.assertIn("main { position: relative; min-width: 0; min-height: 0; overflow: hidden; }", css)
        self.assertIn("flex-wrap: wrap", css)
        self.assertIn("#studio-frame { display: block; width: 100%; height: 100%", css)


if __name__ == "__main__":
    unittest.main()

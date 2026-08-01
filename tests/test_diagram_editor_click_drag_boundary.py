from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_editor_exports import enhance_diagram_editor_exports_html
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.transition_layout_interaction_adapter import (
    enhance_transition_layout_interaction_adapter_html,
)


class DiagramEditorClickDragBoundaryTests(unittest.TestCase):
    def test_graph_node_click_does_not_persist_or_reroute(self) -> None:
        html = enhance_diagram_editor_exports_html(DIAGRAM_HTML)

        self.assertIn("DRAG_THRESHOLD=3", html)
        self.assertIn("moved:false", html)
        self.assertIn("Math.hypot(dx,dy)<DRAG_THRESHOLD", html)
        self.assertIn("drag.moved=true", html)
        self.assertIn("const moved=drag.moved", html)
        self.assertIn("if(!moved)return;\n      save(stage);", html)

    def test_transition_label_boundary_belongs_to_interaction_adapter(self) -> None:
        html = enhance_transition_layout_interaction_adapter_html(DIAGRAM_HTML)

        self.assertIn("DRAG_THRESHOLD=3", html)
        self.assertIn("dragged:false", html)
        self.assertIn("finalPoint:null", html)
        self.assertIn("pointerDistance(active,event)<DRAG_THRESHOLD", html)
        self.assertIn("active.dragged=true;active.finalPoint=point", html)
        self.assertIn("if(!record.dragged||!record.finalPoint)return", html)
        self.assertIn("setPointerCapture?.(event.pointerId)", html)
        self.assertIn("releasePointerCapture?.(event.pointerId)", html)
        self.assertIn("manual-label-persisted", html)

    def test_manual_label_is_snapped_before_canonical_persistence(self) -> None:
        html = enhance_transition_layout_interaction_adapter_html(DIAGRAM_HTML)

        self.assertIn("nearestCertifiablePoint", html)
        self.assertIn("manualPlacementViolation", html)
        self.assertIn("route-foreign-label", html)
        self.assertIn("label-node-overlap", html)
        self.assertIn("label-label-overlap", html)
        self.assertIn("manualIoAdjusted", html)
        self.assertIn("manual-label-rejected", html)
        self.assertLess(
            html.index("nearestCertifiablePoint(record,requested)"),
            html.index("writeStored(key,saved)"),
        )

    def test_enhancers_are_idempotent(self) -> None:
        editor_once = enhance_diagram_editor_exports_html(DIAGRAM_HTML)
        editor_twice = enhance_diagram_editor_exports_html(editor_once)
        self.assertEqual(editor_once, editor_twice)

        interaction_once = enhance_transition_layout_interaction_adapter_html(DIAGRAM_HTML)
        interaction_twice = enhance_transition_layout_interaction_adapter_html(
            interaction_once
        )
        self.assertEqual(interaction_once, interaction_twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_transition_layout_interaction_adapter_html(
            enhance_diagram_editor_exports_html(DIAGRAM_HTML)
        )
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "diagram-editor-click-drag-boundary.js"
            script.write_text("\n".join(scripts), encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(script)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

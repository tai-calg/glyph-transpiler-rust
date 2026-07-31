from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_editor_exports import enhance_diagram_editor_exports_html
from glyph.diagram_ui import DIAGRAM_HTML


class DiagramEditorClickDragBoundaryTests(unittest.TestCase):
    def test_state_node_click_does_not_persist_or_reroute(self) -> None:
        html = enhance_diagram_editor_exports_html(DIAGRAM_HTML)

        self.assertIn("DRAG_THRESHOLD=3", html)
        self.assertIn("moved:false", html)
        self.assertIn("Math.hypot(dx,dy)<DRAG_THRESHOLD", html)
        self.assertIn("drag.moved=true", html)
        self.assertIn("const moved=drag.moved", html)
        self.assertIn("if(!moved)return;\n      save(stage);", html)

    def test_transition_label_uses_the_same_click_drag_boundary(self) -> None:
        html = enhance_diagram_editor_exports_html(DIAGRAM_HTML)

        self.assertIn("ioDrag.moved=true", html)
        self.assertIn("const moved=ioDrag.moved", html)
        self.assertIn("if(!moved)return;\n      cluster.dataset.manualIo", html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_diagram_editor_exports_html(DIAGRAM_HTML)
        twice = enhance_diagram_editor_exports_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_diagram_editor_exports_html(DIAGRAM_HTML)
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

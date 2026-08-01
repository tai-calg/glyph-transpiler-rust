from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_editor_exports import enhance_diagram_editor_exports_html
from glyph.diagram_ui import DIAGRAM_HTML


class DiagramEditorExportTests(unittest.TestCase):
    def test_enhancer_adds_graph_editor_themes_and_exports(self) -> None:
        html = enhance_diagram_editor_exports_html(DIAGRAM_HTML)
        self.assertIn("glyph-diagram-editor-exports-v1", html)
        self.assertIn('id="diagram-theme"', html)
        self.assertIn('id="diagram-svg"', html)
        self.assertIn('id="diagram-png"', html)
        self.assertIn('id="diagram-pdf"', html)
        self.assertIn("theme-monochrome", html)
        self.assertIn("localStorage.setItem(key(stage)", html)
        self.assertIn("state-transition-path", html)
        self.assertIn("application/pdf", html)
        self.assertIn("version:2", html)

    def test_state_nodes_are_owned_only_by_transition_position_adapter(self) -> None:
        html = enhance_diagram_editor_exports_html(DIAGRAM_HTML)

        self.assertIn(
            'stage.dataset.stateNodeInteractionOwner="glyph-transition-node-position-adapter-v7"',
            html,
        )
        self.assertIn(
            'stateNodeInteractionOwner:"glyph-transition-node-position-adapter-v7"',
            html,
        )
        self.assertIn('stage.querySelectorAll(".graph-node").forEach(node=>', html)
        self.assertNotIn('stage.querySelectorAll(".state-node,.graph-node").forEach(node=>', html)
        self.assertIn('!selected.matches(".graph-node")', html)
        self.assertNotIn("function stateCurve(", html)
        self.assertNotIn('document.dispatchEvent(new CustomEvent("glyph-transition-input-action-labels-ready"))', html)

    def test_reset_resolves_digest_before_removing_position_storage(self) -> None:
        html = enhance_diagram_editor_exports_html(DIAGRAM_HTML)

        self.assertIn('$("#diagram-reset").onclick=async()=>', html)
        self.assertIn("await state();localStorage.removeItem(key(stage))", html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_diagram_editor_exports_html(DIAGRAM_HTML)
        twice = enhance_diagram_editor_exports_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_diagram_editor_exports_html(DIAGRAM_HTML)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "diagram-editor-exports.js"
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

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_ui import DIAGRAM_HTML
from glyph.transition_node_position_adapter import (
    enhance_transition_node_position_adapter_html,
)


class TransitionNodePositionAdapterTests(unittest.TestCase):
    def test_adapter_exclusively_owns_actual_node_drags(self) -> None:
        html = enhance_transition_node_position_adapter_html(DIAGRAM_HTML)

        self.assertIn("DRAG_THRESHOLD=3", html)
        self.assertIn("moved:false", html)
        self.assertIn("pointerDistance(active,event)<DRAG_THRESHOLD", html)
        self.assertIn("active.moved=true", html)
        self.assertIn("event.stopImmediatePropagation()", html)
        self.assertIn("record.positions=snapshot(record.stage)", html)
        self.assertIn("manual-node-persisted", html)
        self.assertIn("version:4", html)

    def test_simple_click_neither_moves_nor_persists(self) -> None:
        html = enhance_transition_node_position_adapter_html(DIAGRAM_HTML)

        self.assertIn("positionStorageState", html)
        self.assertIn("restorePositionStorageState", html)
        self.assertIn("storageBefore:positionStorageState()", html)
        self.assertIn("if(!record.moved)", html)
        self.assertIn(
            "setTimeout(()=>restorePositionStorageState(record.storageBefore),0)",
            html,
        )
        self.assertNotIn(
            "queueMicrotask(()=>restorePositionStorageState(record.storageBefore))",
            html,
        )

    def test_keyboard_move_uses_the_same_transaction_boundary(self) -> None:
        html = enhance_transition_node_position_adapter_html(DIAGRAM_HTML)

        self.assertIn('document.addEventListener("keydown"', html)
        self.assertIn('document.querySelector(".state-node.selected-node")', html)
        self.assertIn("transition node keyboard persistence failed", html)
        self.assertIn("persist(record)", html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_transition_node_position_adapter_html(DIAGRAM_HTML)
        twice = enhance_transition_node_position_adapter_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_injected_javascript_is_syntactically_valid(self) -> None:
        html = enhance_transition_node_position_adapter_html(DIAGRAM_HTML)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "transition-node-position-adapter.js"
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

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
    def test_only_actual_node_drags_are_persisted(self) -> None:
        html = enhance_transition_node_position_adapter_html(DIAGRAM_HTML)

        self.assertIn("DRAG_THRESHOLD=3", html)
        self.assertIn("positionStorageState", html)
        self.assertIn("restorePositionStorageState", html)
        self.assertIn("storageBefore:positionStorageState()", html)
        self.assertIn("pointerDistance<DRAG_THRESHOLD&&visualDistance<1", html)
        self.assertIn(
            "queueMicrotask(()=>restorePositionStorageState(record.storageBefore))",
            html,
        )
        self.assertIn("record.positions=snapshot(record.stage)", html)
        self.assertIn("manual-node-persisted", html)

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

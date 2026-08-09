from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_gui_ux_guard import _SCRIPT, _STYLE, enhance_diagram_gui_ux_guard_html
from glyph.readable_diagram_app import _presentation_pipeline


def _javascript(source: str) -> str:
    match = re.search(r"<script[^>]*>\n(.*)\n</script>", source, re.DOTALL)
    return match.group(1) if match else source


class DiagramGuiUxGuardTests(unittest.TestCase):
    def test_guard_runs_after_editor_and_interaction_owners(self) -> None:
        names = [enhancer.__name__ for enhancer in _presentation_pipeline()]
        guard = names.index("enhance_diagram_gui_ux_guard_html")
        self.assertGreater(guard, names.index("enhance_editor_completion_html"))
        self.assertGreater(guard, names.index("enhance_transition_node_position_adapter_html"))
        self.assertGreater(guard, names.index("enhance_transition_layout_interaction_adapter_html"))

    def test_guard_covers_keyboard_focus_pointer_and_narrow_layout(self) -> None:
        self.assertIn("@media(max-width:680px)", _STYLE)
        self.assertIn('group.setAttribute("role","tablist")', _SCRIPT)
        self.assertIn('tab.setAttribute("aria-selected"', _SCRIPT)
        self.assertIn('event.key==="ArrowRight"', _SCRIPT)
        self.assertIn('node.addEventListener("focus"', _SCRIPT)
        self.assertIn('cluster.setAttribute("aria-haspopup","dialog")', _SCRIPT)
        self.assertIn('glyph-transition-label-inspector-opened', _SCRIPT)
        self.assertIn('document.querySelector("dialog[open]")', _SCRIPT)
        self.assertIn('saveShortcut', _SCRIPT)
        self.assertIn('splitter.addEventListener("pointercancel"', _SCRIPT)
        self.assertIn('window.addEventListener("blur"', _SCRIPT)
        self.assertIn('legacyLabel.dispatchEvent(new PointerEvent("pointerup"', _SCRIPT)

    def test_enhancer_is_idempotent(self) -> None:
        html = "<html><head></head><body></body></html>"
        once = enhance_diagram_gui_ux_guard_html(html)
        twice = enhance_diagram_gui_ux_guard_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_embedded_javascript_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gui-ux-guard.js"
            path.write_text(_javascript(_SCRIPT), encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(path)], capture_output=True, text=True, check=False
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

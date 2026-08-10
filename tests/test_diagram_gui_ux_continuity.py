from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_gui_ux_continuity import (
    _SCRIPT,
    _STYLE,
    enhance_diagram_gui_ux_continuity_html,
)
from glyph.readable_diagram_app import _presentation_pipeline


def _javascript(source: str) -> str:
    match = re.search(r"<script[^>]*>\n(.*)\n</script>", source, re.DOTALL)
    return match.group(1) if match else source


class DiagramGuiUxContinuityTests(unittest.TestCase):
    def test_continuity_guard_is_last_gui_owner(self) -> None:
        names = [enhancer.__name__ for enhancer in _presentation_pipeline()]
        self.assertGreater(
            names.index("enhance_diagram_gui_ux_continuity_html"),
            names.index("enhance_diagram_gui_ux_guard_html"),
        )

    def test_remaining_keyboard_and_focus_paths_are_covered(self) -> None:
        self.assertIn(".graph-node[data-line]:focus-visible", _STYLE)
        self.assertIn(".type-card[data-line]:focus-visible", _STYLE)
        self.assertIn(".edge-label[data-line]:focus-visible", _STYLE)
        self.assertIn(".graph-node[data-line]", _SCRIPT)
        self.assertIn(".type-card[data-line]", _SCRIPT)
        self.assertIn('event.key!=="Enter"&&event.key!==" "', _SCRIPT)
        self.assertIn('typeof globalThis.jumpToLine==="function"', _SCRIPT)
        self.assertIn("globalThis.jumpToLine(line)", _SCRIPT)
        self.assertIn('element.dataset.guiUxContinuityJumpReady="true"', _SCRIPT)
        self.assertIn("event.stopImmediatePropagation();activateLineJump", _SCRIPT)
        self.assertIn('shell.setAttribute("aria-keyshortcuts"', _SCRIPT)
        self.assertIn('if(event.key==="ArrowRight")dx=step', _SCRIPT)
        self.assertIn('modal&&(saveShortcut||diagramZoom||command&&event.key==="Enter")', _SCRIPT)
        self.assertIn('modal&&event.key==="Escape"', _SCRIPT)
        self.assertIn('modal&&event.key==="Tab"', _SCRIPT)
        self.assertIn('const saveShortcut=modal&&command&&event.key.toLowerCase()==="s"', _SCRIPT)
        self.assertIn('const diagramZoom=modal&&command&&["+","=","-","0"].includes(event.key)', _SCRIPT)
        self.assertIn("MODAL_EDITING", _SCRIPT)
        self.assertIn('if(!event.target?.closest?.(MODAL_EDITING)&&event.key.startsWith("Arrow"))', _SCRIPT)
        self.assertIn("MODAL_FOCUSABLE", _SCRIPT)
        self.assertIn("function modalFocusables(modal)", _SCRIPT)
        self.assertIn("function trapModalTab(event,modal)", _SCRIPT)
        self.assertIn('element.getClientRects().length>0', _SCRIPT)
        self.assertIn("FOCUS_REQUEST_TTL_MS=2000", _SCRIPT)
        self.assertIn("const diagramDigest=()", _SCRIPT)
        self.assertIn("diagramDigest:diagramDigest()", _SCRIPT)
        self.assertIn("diagramDigest()!==expected.diagramDigest", _SCRIPT)
        self.assertIn("armNodeFocus(nodeName(node))", _SCRIPT)
        self.assertIn("machineIndex:machineIndex()", _SCRIPT)
        self.assertIn("machineIndex()!==expected.machineIndex", _SCRIPT)
        self.assertIn("restoreNodeFocus()", _SCRIPT)
        self.assertIn("function clearPendingControlFocus()", _SCRIPT)
        self.assertIn("pendingControlFocusTimer", _SCRIPT)
        self.assertIn("active===document.body", _SCRIPT)
        self.assertIn("function armControlFocus(target)", _SCRIPT)
        self.assertIn('target.id==="machine-select"||target.id==="system-select"', _SCRIPT)
        self.assertIn("function restoreControlFocus()", _SCRIPT)
        self.assertIn('window.addEventListener("change",event=>armControlFocus(event.target),true)', _SCRIPT)
        self.assertIn('element.dataset.guiUxContinuityLabel="true"', _SCRIPT)
        self.assertIn('document.documentElement.lang', _SCRIPT)
        self.assertIn('dialog.addEventListener("close"', _SCRIPT)
        self.assertIn('button.focus({preventScroll:true})', _SCRIPT)
        self.assertIn('event.key!=="Tab"', _SCRIPT)
        self.assertIn('completionOpen=editor.getAttribute("aria-expanded")==="true"', _SCRIPT)
        self.assertIn('if(!event.shiftKey&&completionOpen)return', _SCRIPT)
        self.assertIn('window.GlyphEditorCompletion?.close?.()', _SCRIPT)
        self.assertIn('runtime.replaceRange(start,end,"  ")', _SCRIPT)
        self.assertIn('line.replace(/^(?:\\t| {1,2})/,"")', _SCRIPT)
        self.assertIn('window.addEventListener("keydown",handleEditorTab,true)', _SCRIPT)
        self.assertIn("version:5", _SCRIPT)

    def test_enhancer_is_idempotent(self) -> None:
        html = "<html><head></head><body></body></html>"
        once = enhance_diagram_gui_ux_continuity_html(html)
        twice = enhance_diagram_gui_ux_continuity_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_embedded_javascript_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gui-ux-continuity.js"
            path.write_text(_javascript(_SCRIPT), encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

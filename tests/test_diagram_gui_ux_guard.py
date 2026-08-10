from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_gui_ux_guard import _SCRIPT, _STYLE, enhance_diagram_gui_ux_guard_html
from glyph.readable_diagram_app import _presentation_pipeline
from glyph.transition_layout_interaction_adapter import _SCRIPT as LABEL_INTERACTION_SCRIPT


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
        self.assertIn('panel.setAttribute("role","tabpanel")', _SCRIPT)
        self.assertIn('panel.setAttribute("aria-labelledby",activeId)', _SCRIPT)
        self.assertIn('event.key==="ArrowRight"', _SCRIPT)
        self.assertIn('node.addEventListener("focus"', _SCRIPT)
        self.assertIn('cluster.setAttribute("aria-haspopup","dialog")', _SCRIPT)
        self.assertIn('adapter?.keyboardNudge?.(cluster,dx,dy)', _SCRIPT)
        self.assertIn('adapter?.resetCluster?.(cluster)', _SCRIPT)
        self.assertIn('glyph-transition-label-inspector-opened', _SCRIPT)
        self.assertIn("function inspectorIdentityFor(opener)", _SCRIPT)
        self.assertIn("function restoreInspectorOpener(opener,identity)", _SCRIPT)
        self.assertIn("inspectorOpenerIdentity=inspectorIdentityFor(inspectorOpener)", _SCRIPT)
        self.assertIn("clusterDigest(replacement)!==identity.diagramDigest", _SCRIPT)
        self.assertIn('splitter.setAttribute("role","separator")', _SCRIPT)
        self.assertIn('splitter.setAttribute("aria-valuemin","25")', _SCRIPT)
        self.assertIn('if(event.key==="Home")next=25', _SCRIPT)
        self.assertIn('button.setAttribute("aria-haspopup","dialog")', _SCRIPT)
        self.assertIn('document.querySelector("dialog[open]")', _SCRIPT)
        self.assertIn('if(saveShortcut||diagramZoom)', _SCRIPT)
        self.assertIn('splitter.addEventListener("pointercancel"', _SCRIPT)
        self.assertIn('window.addEventListener("pointerdown"', _SCRIPT)
        self.assertIn('window.addEventListener("lostpointercapture"', _SCRIPT)
        self.assertIn('node.dispatchEvent(new PointerEvent("pointercancel"', _SCRIPT)
        self.assertIn('window.addEventListener("blur"', _SCRIPT)
        self.assertIn('legacyLabel.dispatchEvent(new PointerEvent("pointerup"', _SCRIPT)
        self.assertIn("FOCUS_REQUEST_TTL_MS=2000", _SCRIPT)
        self.assertIn("const clusterDigest=cluster=>", _SCRIPT)
        self.assertIn("diagramDigest:clusterDigest(cluster)", _SCRIPT)
        self.assertIn("clusterDigest(cluster)!==expected.diagramDigest", _SCRIPT)
        self.assertIn("function clearPendingClusterFocus()", _SCRIPT)
        self.assertIn("pendingClusterFocusTimer", _SCRIPT)
        self.assertIn("version:4", _SCRIPT)

    def test_transition_label_adapter_exposes_keyboard_placement_contract(self) -> None:
        self.assertIn("async function keyboardNudge(cluster,dx,dy)", LABEL_INTERACTION_SCRIPT)
        self.assertIn('publicationGuard()?.invalidate?.(stage,"manual-label-keyboard")', LABEL_INTERACTION_SCRIPT)
        self.assertIn("await persist(record)", LABEL_INTERACTION_SCRIPT)
        self.assertIn("machineIndex:machineIndex()", LABEL_INTERACTION_SCRIPT)
        self.assertIn("machineIndex()!==record.machineIndex", LABEL_INTERACTION_SCRIPT)
        self.assertIn("storageKey(data,record.machineIndex)", LABEL_INTERACTION_SCRIPT)
        self.assertIn("version:6", LABEL_INTERACTION_SCRIPT)
        self.assertIn("keyboardNudge,resetCluster", LABEL_INTERACTION_SCRIPT)

    def test_enhancer_is_idempotent(self) -> None:
        html = "<html><head></head><body></body></html>"
        once = enhance_diagram_gui_ux_guard_html(html)
        twice = enhance_diagram_gui_ux_guard_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_embedded_javascript_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for name, source in (
                ("gui-ux-guard.js", _SCRIPT),
                ("transition-label-interaction.js", LABEL_INTERACTION_SCRIPT),
            ):
                path = Path(directory) / name
                path.write_text(_javascript(source), encoding="utf-8")
                result = subprocess.run(
                    ["node", "--check", str(path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()

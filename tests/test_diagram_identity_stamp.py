from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.diagram_identity_stamp import _SCRIPT, enhance_diagram_identity_stamp_html
from glyph.readable_diagram_app import _presentation_pipeline


def _javascript(source: str) -> str:
    match = re.search(r"<script[^>]*>\n(.*)\n</script>", source, re.DOTALL)
    return match.group(1) if match else source


class DiagramIdentityStampTests(unittest.TestCase):
    def test_identity_prefers_the_rendered_snapshot_digest(self) -> None:
        self.assertIn('state?.rendered_digest||state?.digest||"source"', _SCRIPT)
        self.assertIn('stage.dataset.diagramDigest=digest', _SCRIPT)
        self.assertIn('new MutationObserver(schedule).observe(view,{childList:true,subtree:true})', _SCRIPT)
        self.assertIn('"glyph-save-state-changed"', _SCRIPT)

    def test_stamp_runs_before_viewport_and_gui_focus_owners(self) -> None:
        names = [enhancer.__name__ for enhancer in _presentation_pipeline()]
        stamp = names.index("enhance_diagram_identity_stamp_html")
        self.assertLess(stamp, names.index("enhance_diagram_canvas_viewport_html"))
        self.assertLess(stamp, names.index("enhance_diagram_gui_ux_guard_html"))
        self.assertLess(stamp, names.index("enhance_diagram_gui_ux_continuity_html"))

    def test_enhancer_is_idempotent(self) -> None:
        html = "<html><head></head><body></body></html>"
        once = enhance_diagram_identity_stamp_html(html)
        twice = enhance_diagram_identity_stamp_html(once)
        self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_embedded_javascript_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagram-identity-stamp.js"
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

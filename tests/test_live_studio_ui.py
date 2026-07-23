from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.live_studio_ui import LIVE_STUDIO_HTML


class LiveStudioUiTests(unittest.TestCase):
    def test_live_view_keeps_base_studio_features(self) -> None:
        for marker in (
            "Semantic design workspace",
            "Live Image",
            "function liveImageView",
            "function performLiveAction",
            "function capabilityView",
            "function renderInspector",
            "Auto preview",
            "Ctrl/Cmd+K",
        ):
            self.assertIn(marker, LIVE_STUDIO_HTML)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_live_studio_javascript_is_syntactically_valid(self) -> None:
        match = re.search(r"<script>(.*)</script>", LIVE_STUDIO_HTML, re.DOTALL)
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "live-studio.js"
            script.write_text(match.group(1), encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(script)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

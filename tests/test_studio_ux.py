from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from glyph.studio import GlyphStudio
from glyph.studio_ui import STUDIO_HTML


class GlyphStudioUxTests(unittest.TestCase):
    def test_preview_compiles_unsaved_source_without_writing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.glyph"
            original = ">inc(x:U):U=x+1\n"
            preview = ">double(x:U):U=x*2\n"
            source.write_text(original, encoding="utf-8")

            studio = GlyphStudio(source)
            studio.rebuild()
            server = studio.create_server()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            try:
                payload = json.dumps({"source": preview}).encode("utf-8")
                request = Request(
                    f"http://{host}:{port}/api/preview",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request) as response:
                    state = json.loads(response.read().decode("utf-8"))

                self.assertEqual(state["status"], "ready")
                self.assertEqual(state["source"], preview)
                self.assertEqual(source.read_text(encoding="utf-8"), original)
                self.assertIn("pub fn double", studio.artifact("generated.rs") or "")

                rebuild = Request(
                    f"http://{host}:{port}/api/rebuild",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(rebuild) as response:
                    restored = json.loads(response.read().decode("utf-8"))
                self.assertEqual(restored["source"], original)
                self.assertIn("pub fn inc", studio.artifact("generated.rs") or "")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1.0)

    def test_preview_requires_text_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.glyph"
            source.write_text(">inc(x:U):U=x+1\n", encoding="utf-8")
            studio = GlyphStudio(source)
            studio.rebuild()
            server = studio.create_server()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            try:
                request = Request(
                    f"http://{host}:{port}/api/preview",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as raised:
                    urlopen(request)
                self.assertEqual(raised.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1.0)

    def test_watcher_does_not_replace_unsaved_preview_without_disk_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.glyph"
            source.write_text(">inc(x:U):U=x+1\n", encoding="utf-8")
            studio = GlyphStudio(source)
            studio.rebuild()
            studio.start_watching(interval=0.05)
            try:
                preview = ">double(x:U):U=x*2\n"
                studio.preview_source(preview)
                time.sleep(0.16)
                self.assertEqual(studio.snapshot.source, preview)
            finally:
                studio.stop()

    def test_ui_contains_refined_workspace_controls(self) -> None:
        for marker in (
            "view-nav",
            "splitter",
            "Auto preview",
            "Filter this view",
            "Toggle theme",
            "Toggle editor",
            "Preview without saving",
            "glyphStudio.editorWidth",
            "glyphStudio.activeView",
            "/api/preview",
            "Ctrl/Cmd+Enter",
        ):
            self.assertIn(marker, STUDIO_HTML)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_studio_javascript_is_syntactically_valid(self) -> None:
        match = re.search(r"<script>(.*)</script>", STUDIO_HTML, re.DOTALL)
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "studio.js"
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

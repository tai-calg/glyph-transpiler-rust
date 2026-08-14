from __future__ import annotations

from http import HTTPStatus
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from glyph.desktop_server import create_desktop_server
from glyph.source_file_picker import (
    SourceSelectionError,
    enhance_source_file_picker_html,
    find_source_picker_root,
    resolve_source_selection,
    source_file_catalog,
)


SOURCE_A = ">identity(x:U):U=x\n"
SOURCE_B = ">double(x:U):U=x*2\n"


class SourceFilePickerTests(unittest.TestCase):
    def test_catalog_defaults_to_configured_examples_and_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            examples = root / "examples"
            examples.mkdir()
            current = examples / "a.glyph"
            nested = examples / "nested" / "b.glyph"
            nested.parent.mkdir()
            current.write_text(SOURCE_A, encoding="utf-8")
            nested.write_text(SOURCE_B, encoding="utf-8")
            (root / "outside.glyph").write_text(SOURCE_A, encoding="utf-8")

            with patch.dict(os.environ, {"GLYPH_EXAMPLES_DIR": str(examples)}):
                selected_root = find_source_picker_root(current)
            self.assertEqual(selected_root, examples.resolve())

            catalog = source_file_catalog(selected_root, current)
            self.assertEqual(catalog["current"], "a.glyph")
            self.assertEqual(
                [item["path"] for item in catalog["files"]],
                ["a.glyph", "nested/b.glyph"],
            )
            self.assertEqual(
                resolve_source_selection(selected_root, "nested/b.glyph"),
                nested.resolve(),
            )
            with self.assertRaises(SourceSelectionError):
                resolve_source_selection(selected_root, "../outside.glyph")

    def test_enhancer_reuses_path_label_as_layout_neutral_file_trigger(self) -> None:
        html = (
            '<html><head></head><body><header>'
            '<div class="path" id="path">example.glyph</div>'
            '<div class="status" id="status">ready</div>'
            '</header></body></html>'
        )
        enhanced = enhance_source_file_picker_html(html)
        enhanced_twice = enhance_source_file_picker_html(enhanced)

        self.assertEqual(enhanced, enhanced_twice)
        self.assertEqual(enhanced.count('<div class="path" id="path">'), 1)
        self.assertIn('id="source-file-menu"', enhanced)
        self.assertIn('id="source-file-select"', enhanced)
        self.assertIn('source-file-menu[hidden]{display:none!important}', enhanced)
        self.assertIn("trigger.setAttribute('role', 'button')", enhanced)
        self.assertIn("trigger.setAttribute('tabindex', '0')", enhanced)
        self.assertIn("/api/source-files", enhanced)
        self.assertIn("/api/open-source", enhanced)
        self.assertIn("Unsaved editor changes will be discarded", enhanced)

    def test_server_lists_examples_switches_source_and_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            examples = root / "examples"
            examples.mkdir()
            source_a = examples / "a.glyph"
            source_b = examples / "b.glyph"
            outside = root / "outside.glyph"
            source_a.write_text(SOURCE_A, encoding="utf-8")
            source_b.write_text(SOURCE_B, encoding="utf-8")
            outside.write_text(SOURCE_A, encoding="utf-8")

            with patch.dict(os.environ, {"GLYPH_EXAMPLES_DIR": str(examples)}):
                desktop = create_desktop_server(source_a, require_auth=False)
            thread = threading.Thread(target=desktop.server.serve_forever, daemon=True)
            thread.start()
            base = desktop.origin
            try:
                catalog = json.loads(
                    urlopen(f"{base}/api/source-files", timeout=3)
                    .read()
                    .decode("utf-8")
                )
                self.assertEqual(catalog["current"], "a.glyph")
                self.assertEqual(
                    [item["path"] for item in catalog["files"]],
                    ["a.glyph", "b.glyph"],
                )

                switch = Request(
                    f"{base}/api/open-source",
                    data=json.dumps({"path": "b.glyph"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                switched = json.loads(
                    urlopen(switch, timeout=3).read().decode("utf-8")
                )
                self.assertEqual(Path(switched["source_path"]), source_b)
                self.assertEqual(desktop.app.input_path, source_b.resolve())

                traversal = Request(
                    f"{base}/api/open-source",
                    data=json.dumps({"path": "../outside.glyph"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as rejected:
                    urlopen(traversal, timeout=3)
                self.assertEqual(rejected.exception.code, HTTPStatus.BAD_REQUEST)
                self.assertEqual(desktop.app.input_path, source_b.resolve())
            finally:
                desktop.close()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()

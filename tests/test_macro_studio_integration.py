from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen

from glyph.desktop_server import create_desktop_server


INITIAL_SOURCE = "@MAX 10\n>value():I=MAX\n"


def _read_json(url: str) -> dict[str, object]:
    with urlopen(url, timeout=3) as response:
        value = json.loads(response.read().decode("utf-8"))
    assert isinstance(value, dict)
    return value


def _post_source(url: str, source: str) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps({"source": source}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        value = json.loads(response.read().decode("utf-8"))
    assert isinstance(value, dict)
    return value


class MacroStudioIntegrationTests(unittest.TestCase):
    def _start(self, source_path: Path):
        desktop = create_desktop_server(source_path, require_auth=False)
        thread = threading.Thread(target=desktop.server.serve_forever, daemon=True)
        thread.start()
        return desktop, thread

    def test_final_app_html_has_no_compile_on_input_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            desktop, thread = self._start(source_path)
            try:
                with urlopen(desktop.launch_url, timeout=3) as response:
                    html = response.read().decode("utf-8")
                self.assertIn("glyph-save-triggered-rendering-v1", html)
                self.assertIn('id="save"', html)
                self.assertNotIn('id="compile"', html)
                self.assertNotIn("/api/preview", html)
                self.assertNotIn("previewTimer", html)
                self.assertIn(
                    "editor.addEventListener('input',()=>{dirty=true;syncLines()})",
                    html,
                )
            finally:
                desktop.close()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())

    def test_http_save_reprocesses_macros_and_recovers_after_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            desktop, thread = self._start(source_path)
            try:
                initial = _read_json(f"{desktop.origin}/api/state")
                legacy_source = "@EXPR=x + 2\n>value(x:I):I=EXPR\n"
                saved = _post_source(f"{desktop.origin}/api/save", legacy_source)
                self.assertEqual(saved["status"], "ready")
                self.assertGreater(int(saved["version"]), int(initial["version"]))
                self.assertEqual(source_path.read_text(encoding="utf-8"), legacy_source)

                compilation = desktop.app.compiler.last_snapshot
                self.assertIsNotNone(compilation)
                assert compilation is not None
                self.assertIn("x + 2", compilation.artifacts.logic)
                self.assertEqual(
                    compilation.diagrams.files["preprocessed.glyph"],
                    ">value(x:I):I=x + 2\n",
                )

                broken_source = "@MAX\n>value():I=MAX\n"
                broken = _post_source(f"{desktop.origin}/api/save", broken_source)
                self.assertEqual(broken["status"], "error")
                self.assertEqual(
                    source_path.read_text(encoding="utf-8"),
                    broken_source,
                )

                corrected_source = "@MAX 12\n>value():I=MAX\n"
                corrected = _post_source(
                    f"{desktop.origin}/api/save",
                    corrected_source,
                )
                self.assertEqual(corrected["status"], "ready")
                compilation = desktop.app.compiler.last_snapshot
                self.assertIsNotNone(compilation)
                assert compilation is not None
                self.assertIn("12", compilation.artifacts.logic)
                self.assertEqual(
                    compilation.diagrams.files["preprocessed.glyph"],
                    ">value():I=12\n",
                )
            finally:
                desktop.close()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())

    def test_external_file_save_reprocesses_macro_before_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            desktop, thread = self._start(source_path)
            try:
                initial = _read_json(f"{desktop.origin}/api/state")
                updated_source = "@MAX 21\n>value():I=MAX\n"
                source_path.write_text(updated_source, encoding="utf-8")

                deadline = time.monotonic() + 4.0
                state = initial
                while time.monotonic() < deadline:
                    state = _read_json(f"{desktop.origin}/api/state")
                    if state.get("source") == updated_source and state.get("status") == "ready":
                        break
                    time.sleep(0.05)

                self.assertEqual(state.get("source"), updated_source)
                self.assertEqual(state.get("status"), "ready")
                self.assertGreater(int(state["version"]), int(initial["version"]))
                compilation = desktop.app.compiler.last_snapshot
                self.assertIsNotNone(compilation)
                assert compilation is not None
                self.assertIn("21", compilation.artifacts.logic)
                self.assertEqual(
                    compilation.diagrams.files["preprocessed.glyph"],
                    ">value():I=21\n",
                )
            finally:
                desktop.close()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from glyph.desktop_server import create_desktop_server


INITIAL_SOURCE = "@MAX 10\n>value():I=MAX\n"


def _read_json(url: str) -> dict[str, object]:
    with urlopen(url, timeout=3) as response:
        value = json.loads(response.read().decode("utf-8"))
    assert isinstance(value, dict)
    return value


def _post_json(
    url: str,
    payload: dict[str, object],
) -> tuple[int, dict[str, object]]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            value = json.loads(response.read().decode("utf-8"))
            status = response.status
    except HTTPError as exc:
        value = json.loads(exc.read().decode("utf-8"))
        status = exc.code
    assert isinstance(value, dict)
    return status, value


def _save(
    url: str,
    source: str,
    *,
    base_digest: str | None = None,
    force: bool = False,
) -> tuple[int, dict[str, object]]:
    return _post_json(
        url,
        {
            "source": source,
            "base_digest": base_digest,
            "force": force,
        },
    )


class MacroStudioIntegrationTests(unittest.TestCase):
    def _start(self, source_path: Path):
        desktop = create_desktop_server(source_path, require_auth=False)
        thread = threading.Thread(target=desktop.server.serve_forever, daemon=True)
        thread.start()
        return desktop, thread

    def test_final_app_html_has_only_save_triggered_compilation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            desktop, thread = self._start(source_path)
            try:
                with urlopen(desktop.launch_url, timeout=3) as response:
                    html = response.read().decode("utf-8")
                self.assertIn("glyph-save-triggered-rendering-v2", html)
                self.assertIn('id="save"', html)
                self.assertNotIn('id="compile"', html)
                self.assertNotIn("/api/preview", html)
                self.assertNotIn("previewTimer", html)
                self.assertNotIn("previewController", html)
                self.assertIn("base_digest:editorBaseDigest", html)
                self.assertIn("glyph-stale-banner", html)
                self.assertIn("glyph-conflict-dialog", html)
                self.assertIn("beforeunload", html)
                self.assertIn(
                    "editor.addEventListener('input',()=>{dirty=true;syncLines()})",
                    html,
                )

                status, payload = _post_json(
                    f"{desktop.origin}/api/preview",
                    {"source": INITIAL_SOURCE},
                )
                self.assertEqual(status, 404)
                self.assertEqual(payload["error"], "not found")
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
                status, saved = _save(
                    f"{desktop.origin}/api/save",
                    legacy_source,
                    base_digest=str(initial["digest"]),
                )
                self.assertEqual(status, 200)
                self.assertEqual(saved["status"], "ready")
                self.assertEqual(saved["digest"], saved["rendered_digest"])
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
                status, broken = _save(
                    f"{desktop.origin}/api/save",
                    broken_source,
                    base_digest=str(saved["digest"]),
                )
                self.assertEqual(status, 200)
                self.assertEqual(broken["status"], "error")
                self.assertNotEqual(broken["digest"], broken["rendered_digest"])
                self.assertEqual(
                    broken["rendered_digest"],
                    saved["rendered_digest"],
                )
                self.assertEqual(
                    broken["last_successful_version"],
                    saved["last_successful_version"],
                )
                self.assertEqual(
                    source_path.read_text(encoding="utf-8"),
                    broken_source,
                )

                corrected_source = "@MAX 12\n>value():I=MAX\n"
                status, corrected = _save(
                    f"{desktop.origin}/api/save",
                    corrected_source,
                    base_digest=str(broken["digest"]),
                )
                self.assertEqual(status, 200)
                self.assertEqual(corrected["status"], "ready")
                self.assertEqual(
                    corrected["digest"],
                    corrected["rendered_digest"],
                )
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

    def test_stale_base_digest_is_rejected_until_explicit_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            desktop, thread = self._start(source_path)
            try:
                initial = _read_json(f"{desktop.origin}/api/state")
                external_source = "@MAX 30\n>value():I=MAX\n"
                source_path.write_text(external_source, encoding="utf-8")

                deadline = time.monotonic() + 4.0
                external_state = initial
                while time.monotonic() < deadline:
                    external_state = _read_json(f"{desktop.origin}/api/state")
                    if external_state.get("source") == external_source:
                        break
                    time.sleep(0.05)
                self.assertEqual(external_state.get("source"), external_source)

                local_source = "@MAX 31\n>value():I=MAX\n"
                status, conflict = _save(
                    f"{desktop.origin}/api/save",
                    local_source,
                    base_digest=str(initial["digest"]),
                )
                self.assertEqual(status, 409)
                self.assertEqual(conflict["error"], "save_conflict")
                self.assertEqual(conflict["current_source"], external_source)
                self.assertEqual(
                    source_path.read_text(encoding="utf-8"),
                    external_source,
                )

                status, overwritten = _save(
                    f"{desktop.origin}/api/save",
                    local_source,
                    base_digest=str(conflict["current_digest"]),
                    force=True,
                )
                self.assertEqual(status, 200)
                self.assertEqual(overwritten["status"], "ready")
                self.assertEqual(
                    source_path.read_text(encoding="utf-8"),
                    local_source,
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
                self.assertEqual(state.get("digest"), state.get("rendered_digest"))
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

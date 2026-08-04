from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from glyph.desktop_server import create_desktop_server
from glyph.io_state_views import build_io_state_views


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
) -> tuple[int, dict[str, object]]:
    return _post_json(
        url,
        {
            "source": source,
            "base_digest": base_digest,
        },
    )


def _wait_for_state(
    origin: str,
    predicate,
    *,
    timeout: float = 8.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    state: dict[str, object] = {}
    while time.monotonic() < deadline:
        state = _read_json(f"{origin}/api/state")
        if predicate(state):
            return state
        time.sleep(0.03)
    raise AssertionError(f"state did not converge: {state}")


def _wait_for_terminal_source(
    origin: str,
    source: str,
    *,
    expected_status: str = "ready",
    timeout: float = 8.0,
) -> dict[str, object]:
    return _wait_for_state(
        origin,
        lambda state: state.get("source") == source
        and state.get("status") == expected_status,
        timeout=timeout,
    )


class MacroStudioIntegrationTests(unittest.TestCase):
    def _start(self, source_path: Path, *, view_builder=build_io_state_views):
        desktop = create_desktop_server(
            source_path,
            require_auth=False,
            view_builder=view_builder,
        )
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
                self.assertIn("glyph-save-triggered-rendering-v3", html)
                self.assertIn('id="save"', html)
                self.assertNotIn('id="compile"', html)
                self.assertNotIn("/api/preview", html)
                self.assertNotIn("previewTimer", html)
                self.assertNotIn("previewController", html)
                self.assertIn("base_digest:baseDigest||editorBaseDigest||null", html)
                self.assertIn("glyph-stale-banner", html)
                self.assertIn("glyph-conflict-dialog", html)
                self.assertIn("beforeunload", html)
                self.assertIn("event.isComposing", html)
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
                status, accepted = _save(
                    f"{desktop.origin}/api/save",
                    legacy_source,
                    base_digest=str(initial["digest"]),
                )
                self.assertEqual(status, 202)
                self.assertEqual(accepted["source"], legacy_source)
                self.assertIsNotNone(accepted["operation_id"])
                self.assertEqual(source_path.read_text(encoding="utf-8"), legacy_source)

                saved = _wait_for_terminal_source(desktop.origin, legacy_source)
                self.assertEqual(saved["digest"], saved["rendered_digest"])
                self.assertGreater(int(saved["version"]), int(initial["version"]))

                compilation = desktop.app.compiler.last_snapshot
                self.assertIsNotNone(compilation)
                assert compilation is not None
                self.assertIn("x + 2", compilation.artifacts.logic)
                self.assertEqual(
                    compilation.diagrams.files["preprocessed.glyph"],
                    ">value(x:I):I=x + 2\n",
                )

                broken_source = "@MAX\n>value():I=MAX\n"
                status, accepted_broken = _save(
                    f"{desktop.origin}/api/save",
                    broken_source,
                    base_digest=str(saved["digest"]),
                )
                self.assertEqual(status, 202)
                self.assertEqual(accepted_broken["source"], broken_source)
                self.assertEqual(
                    source_path.read_text(encoding="utf-8"),
                    broken_source,
                )
                broken = _wait_for_terminal_source(
                    desktop.origin,
                    broken_source,
                    expected_status="error",
                )
                self.assertNotEqual(broken["digest"], broken["rendered_digest"])
                self.assertEqual(
                    broken["rendered_digest"],
                    saved["rendered_digest"],
                )
                self.assertEqual(
                    broken["last_successful_version"],
                    saved["last_successful_version"],
                )

                corrected_source = "@MAX 12\n>value():I=MAX\n"
                status, _ = _save(
                    f"{desktop.origin}/api/save",
                    corrected_source,
                    base_digest=str(broken["digest"]),
                )
                self.assertEqual(status, 202)
                corrected = _wait_for_terminal_source(desktop.origin, corrected_source)
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

    def test_save_ack_does_not_wait_for_slow_compile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            call_count = 0
            lock = threading.Lock()

            def slow_builder(model, ir):
                nonlocal call_count
                with lock:
                    call_count += 1
                    current = call_count
                if current > 1:
                    time.sleep(1.2)
                return build_io_state_views(model, ir)

            desktop, thread = self._start(source_path, view_builder=slow_builder)
            try:
                initial = _read_json(f"{desktop.origin}/api/state")
                updated_source = "@MAX 22\n>value():I=MAX\n"
                started = time.monotonic()
                status, accepted = _save(
                    f"{desktop.origin}/api/save",
                    updated_source,
                    base_digest=str(initial["digest"]),
                )
                elapsed = time.monotonic() - started
                self.assertEqual(status, 202)
                self.assertLess(elapsed, 0.75)
                self.assertEqual(accepted["status"], "compiling")
                self.assertEqual(source_path.read_text(encoding="utf-8"), updated_source)
                responsive = _read_json(f"{desktop.origin}/api/state")
                self.assertEqual(responsive["source"], updated_source)
                final = _wait_for_terminal_source(
                    desktop.origin,
                    updated_source,
                    timeout=5.0,
                )
                self.assertEqual(final["status"], "ready")
            finally:
                desktop.close()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())

    def test_latest_save_supersedes_in_flight_compile_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            call_count = 0
            lock = threading.Lock()

            def slow_builder(model, ir):
                nonlocal call_count
                with lock:
                    call_count += 1
                    current = call_count
                if current > 1:
                    time.sleep(0.6)
                return build_io_state_views(model, ir)

            desktop, thread = self._start(source_path, view_builder=slow_builder)
            try:
                initial = _read_json(f"{desktop.origin}/api/state")
                first_source = "@MAX 40\n>value():I=MAX\n"
                status, first = _save(
                    f"{desktop.origin}/api/save",
                    first_source,
                    base_digest=str(initial["digest"]),
                )
                self.assertEqual(status, 202)
                second_source = "@MAX 44\n>value():I=MAX\n"
                status, second = _save(
                    f"{desktop.origin}/api/save",
                    second_source,
                    base_digest=str(first["digest"]),
                )
                self.assertEqual(status, 202)
                self.assertNotEqual(first["operation_id"], second["operation_id"])
                final = _wait_for_terminal_source(
                    desktop.origin,
                    second_source,
                    timeout=6.0,
                )
                self.assertEqual(final["digest"], final["rendered_digest"])
                self.assertEqual(source_path.read_text(encoding="utf-8"), second_source)
                compilation = desktop.app.compiler.last_snapshot
                self.assertIsNotNone(compilation)
                assert compilation is not None
                self.assertIn("44", compilation.artifacts.logic)
            finally:
                desktop.close()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())

    def test_stale_base_digest_and_repeated_external_change_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            desktop, thread = self._start(source_path)
            try:
                initial = _read_json(f"{desktop.origin}/api/state")
                external_a = "@MAX 30\n>value():I=MAX\n"
                source_path.write_text(external_a, encoding="utf-8")
                external_a_state = _wait_for_terminal_source(desktop.origin, external_a)

                local_source = "@MAX 31\n>value():I=MAX\n"
                status, conflict_a = _save(
                    f"{desktop.origin}/api/save",
                    local_source,
                    base_digest=str(initial["digest"]),
                )
                self.assertEqual(status, 409)
                self.assertEqual(conflict_a["error"], "save_conflict")
                self.assertEqual(conflict_a["current_source"], external_a)

                external_b = "@MAX 32\n>value():I=MAX\n"
                source_path.write_text(external_b, encoding="utf-8")
                _wait_for_terminal_source(desktop.origin, external_b)

                status, conflict_b = _save(
                    f"{desktop.origin}/api/save",
                    local_source,
                    base_digest=str(conflict_a["current_digest"]),
                )
                self.assertEqual(status, 409)
                self.assertEqual(conflict_b["current_source"], external_b)
                self.assertNotEqual(
                    conflict_a["current_digest"],
                    conflict_b["current_digest"],
                )
                self.assertEqual(source_path.read_text(encoding="utf-8"), external_b)

                status, accepted = _save(
                    f"{desktop.origin}/api/save",
                    local_source,
                    base_digest=str(conflict_b["current_digest"]),
                )
                self.assertEqual(status, 202)
                overwritten = _wait_for_terminal_source(desktop.origin, local_source)
                self.assertEqual(overwritten["operation_id"], accepted["operation_id"])
                self.assertEqual(source_path.read_text(encoding="utf-8"), local_source)
                self.assertGreater(
                    int(overwritten["version"]),
                    int(external_a_state["version"]),
                )
            finally:
                desktop.close()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())

    def test_save_io_failure_is_structured_and_does_not_change_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            desktop, thread = self._start(source_path)
            try:
                initial = _read_json(f"{desktop.origin}/api/state")
                with patch(
                    "glyph.diagram_app._atomic_write",
                    side_effect=PermissionError("read-only source"),
                ):
                    status, payload = _save(
                        f"{desktop.origin}/api/save",
                        "@MAX 99\n>value():I=MAX\n",
                        base_digest=str(initial["digest"]),
                    )
                self.assertEqual(status, 403)
                self.assertEqual(payload["error"], "save_permission_denied")
                self.assertEqual(source_path.read_text(encoding="utf-8"), INITIAL_SOURCE)
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
                state = _wait_for_terminal_source(desktop.origin, updated_source)

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

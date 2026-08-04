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
import uuid

from glyph.desktop_server import create_desktop_server
from glyph.diagram_app import GlyphDiagramApp, SaveOperation
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
    request_id: str | None = None,
) -> tuple[int, dict[str, object]]:
    return _post_json(
        url,
        {
            "request_id": request_id or uuid.uuid4().hex,
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


def _wait_for_save_status(
    origin: str,
    request_id: str,
    expected_status: str,
    *,
    timeout: float = 5.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    operation: dict[str, object] = {}
    while time.monotonic() < deadline:
        operation = _read_json(f"{origin}/api/save-status/{request_id}")
        if operation.get("status") == expected_status:
            return operation
        time.sleep(0.03)
    raise AssertionError(f"save operation did not converge: {operation}")


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
                self.assertIn("glyph-save-triggered-rendering-v4", html)
                self.assertIn('id="save"', html)
                self.assertNotIn('id="compile"', html)
                self.assertNotIn("/api/preview", html)
                self.assertNotIn("previewTimer", html)
                self.assertNotIn("previewController", html)
                self.assertIn("request_id:activeSaveRequestId", html)
                self.assertIn("/api/save-status/", html)
                self.assertIn('fetchJson("/api/status")', html)
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

    def test_status_endpoint_is_lightweight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            desktop, thread = self._start(source_path)
            try:
                status = _read_json(f"{desktop.origin}/api/status")
                self.assertEqual(status["status"], "ready")
                self.assertNotIn("source", status)
                self.assertNotIn("views", status)
                self.assertNotIn("diagnostics", status)
                self.assertIn("diagnostic_count", status)
            finally:
                desktop.close()
                thread.join(timeout=2)

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
                self.assertEqual(accepted["status"], "accepted")
                self.assertIsNotNone(accepted["operation_id"])
                self.assertEqual(
                    accepted["state"]["operation_id"],
                    accepted["operation_id"],
                )
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
                self.assertEqual(accepted_broken["status"], "accepted")
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
                self.assertEqual(accepted["status"], "accepted")
                self.assertEqual(accepted["state"]["status"], "compiling")
                self.assertEqual(source_path.read_text(encoding="utf-8"), updated_source)
                started = time.monotonic()
                responsive = _read_json(f"{desktop.origin}/api/status")
                self.assertLess(time.monotonic() - started, 0.3)
                self.assertEqual(responsive["digest"], accepted["digest"])
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

    def test_request_id_is_idempotent_while_file_write_is_slow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            desktop, thread = self._start(source_path)
            original_atomic_write = __import__(
                "glyph.diagram_app", fromlist=["_atomic_write"]
            )._atomic_write
            entered = threading.Event()
            results: list[tuple[int, dict[str, object]]] = []
            request_id = "tracked-save-request"
            updated_source = "@MAX 23\n>value():I=MAX\n"
            initial = _read_json(f"{desktop.origin}/api/state")

            def slow_atomic_write(path: Path, content: str) -> None:
                if path == source_path:
                    entered.set()
                    time.sleep(0.45)
                original_atomic_write(path, content)

            def first_save() -> None:
                results.append(
                    _save(
                        f"{desktop.origin}/api/save",
                        updated_source,
                        base_digest=str(initial["digest"]),
                        request_id=request_id,
                    )
                )

            try:
                with patch("glyph.diagram_app._atomic_write", side_effect=slow_atomic_write):
                    first = threading.Thread(target=first_save)
                    first.start()
                    self.assertTrue(entered.wait(timeout=1.0))
                    started = time.monotonic()
                    duplicate_status, duplicate = _save(
                        f"{desktop.origin}/api/save",
                        updated_source,
                        base_digest=str(initial["digest"]),
                        request_id=request_id,
                    )
                    self.assertLess(time.monotonic() - started, 0.25)
                    self.assertEqual(duplicate_status, 202)
                    self.assertEqual(duplicate["status"], "saving")
                    first.join(timeout=2)
                    self.assertFalse(first.is_alive())
                self.assertEqual(results[0][0], 202)
                self.assertEqual(results[0][1]["status"], "accepted")
                tracked = _wait_for_save_status(
                    desktop.origin,
                    request_id,
                    "accepted",
                )
                self.assertEqual(tracked["digest"], results[0][1]["digest"])

                mismatch_status, mismatch = _save(
                    f"{desktop.origin}/api/save",
                    updated_source + "# different\n",
                    base_digest=str(initial["digest"]),
                    request_id=request_id,
                )
                self.assertEqual(mismatch_status, 409)
                self.assertEqual(mismatch["error"], "save_request_mismatch")
            finally:
                desktop.close()
                thread.join(timeout=2)

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
                self.assertEqual(
                    first["state"]["operation_id"],
                    first["operation_id"],
                )
                self.assertEqual(
                    second["state"]["operation_id"],
                    second["operation_id"],
                )
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

    def test_worker_unexpected_exception_becomes_error_and_worker_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            calls = 0

            def failing_once_builder(model, ir):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("unexpected layout failure")
                return build_io_state_views(model, ir)

            desktop, thread = self._start(
                source_path,
                view_builder=failing_once_builder,
            )
            try:
                initial = _read_json(f"{desktop.origin}/api/state")
                failing_source = "@MAX 55\n>value():I=MAX\n"
                status, accepted = _save(
                    f"{desktop.origin}/api/save",
                    failing_source,
                    base_digest=str(initial["digest"]),
                )
                self.assertEqual(status, 202)
                failed = _wait_for_terminal_source(
                    desktop.origin,
                    failing_source,
                    expected_status="error",
                )
                self.assertEqual(
                    failed["diagnostics"][0]["code"],
                    "internal_compile_error",
                )
                self.assertIn(
                    "unexpected layout failure",
                    failed["diagnostics"][0]["message"],
                )

                recovered_source = "@MAX 56\n>value():I=MAX\n"
                status, recovered_operation = _save(
                    f"{desktop.origin}/api/save",
                    recovered_source,
                    base_digest=str(accepted["digest"]),
                )
                self.assertEqual(status, 202)
                recovered = _wait_for_terminal_source(
                    desktop.origin,
                    recovered_source,
                )
                self.assertEqual(
                    recovered["operation_id"],
                    recovered_operation["operation_id"],
                )
                self.assertTrue(desktop.app._compile_worker.is_alive())
            finally:
                desktop.close()
                thread.join(timeout=2)

    def test_artifact_serialization_does_not_block_status_or_new_save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            desktop, thread = self._start(source_path)
            original_write_text = Path.write_text
            artifact_write_entered = threading.Event()

            def slow_write_text(path: Path, data: str, *args, **kwargs):
                if path.name.startswith(".io-state-views.json."):
                    artifact_write_entered.set()
                    time.sleep(0.45)
                return original_write_text(path, data, *args, **kwargs)

            try:
                initial = _read_json(f"{desktop.origin}/api/state")
                source = "@MAX 61\n>value():I=MAX\n"
                with patch.object(Path, "write_text", new=slow_write_text):
                    status, accepted = _save(
                        f"{desktop.origin}/api/save",
                        source,
                        base_digest=str(initial["digest"]),
                    )
                    self.assertEqual(status, 202)
                    self.assertTrue(artifact_write_entered.wait(timeout=2.0))
                    started = time.monotonic()
                    lightweight = _read_json(f"{desktop.origin}/api/status")
                    self.assertLess(time.monotonic() - started, 0.25)
                    self.assertEqual(lightweight["digest"], accepted["digest"])
                final = _wait_for_terminal_source(desktop.origin, source)
                self.assertEqual(final["status"], "ready")
            finally:
                desktop.close()
                thread.join(timeout=2)

    def test_same_clean_source_is_noop_while_ready_or_compiling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            desktop, thread = self._start(source_path)
            try:
                initial = _read_json(f"{desktop.origin}/api/state")
                with patch("glyph.diagram_app._atomic_write") as atomic_write:
                    status, accepted = _save(
                        f"{desktop.origin}/api/save",
                        INITIAL_SOURCE,
                        base_digest=str(initial["digest"]),
                    )
                self.assertEqual(status, 202)
                self.assertEqual(accepted["status"], "accepted")
                self.assertEqual(accepted["state"]["status"], "ready")
                atomic_write.assert_not_called()
                after = _read_json(f"{desktop.origin}/api/state")
                self.assertEqual(after["version"], initial["version"])
            finally:
                desktop.close()
                thread.join(timeout=2)

    def test_stop_prevents_late_artifact_and_snapshot_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            entered = threading.Event()
            release = threading.Event()
            calls = 0

            def blocked_builder(model, ir):
                nonlocal calls
                calls += 1
                if calls > 1:
                    entered.set()
                    release.wait(timeout=3.0)
                return build_io_state_views(model, ir)

            app = GlyphDiagramApp(source_path, view_builder=blocked_builder)
            initial = app.rebuild()
            initial_artifact = app.output_path.read_text(encoding="utf-8")
            operation = app.submit_save(
                "@MAX 70\n>value():I=MAX\n",
                base_digest=initial.digest,
                request_id="stop-publication",
            )
            self.assertEqual(operation.status, "accepted")
            self.assertTrue(entered.wait(timeout=1.0))
            app.stop()
            release.set()
            time.sleep(0.2)
            self.assertEqual(
                app.output_path.read_text(encoding="utf-8"),
                initial_artifact,
            )
            self.assertEqual(app.snapshot.status, "error")
            self.assertEqual(
                app.snapshot.diagnostics[0]["code"],
                "server_stopping",
            )
            self.assertEqual(app.snapshot.rendered_digest, initial.rendered_digest)
            self.assertEqual(
                list(app.output_path.parent.glob(".io-state-views.json.*.tmp")),
                [],
            )

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
                self.assertEqual(payload["status"], "error")
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

    def test_saving_operation_is_not_evicted_from_bounded_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            app = GlyphDiagramApp(source_path)
            saving = SaveOperation(
                request_id="active-saving",
                status="saving",
                source_digest="saving-digest",
                base_digest=None,
                http_status=202,
                updated_at="now",
            )
            app._remember_save_operation(saving)
            for index in range(256):
                app._remember_save_operation(
                    SaveOperation(
                        request_id=f"terminal-{index}",
                        status="accepted",
                        source_digest=f"digest-{index}",
                        base_digest=None,
                        http_status=202,
                        updated_at="now",
                    )
                )
            self.assertEqual(
                app.save_request_dict("active-saving")["status"],
                "saving",
            )
            self.assertLessEqual(len(app._save_operations), 256)

    def test_unexpected_save_exception_becomes_terminal_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            app = GlyphDiagramApp(source_path)
            app.rebuild()
            with patch.object(
                app,
                "_persist_source",
                side_effect=RuntimeError("unexpected persistence failure"),
            ):
                operation = app.submit_save(
                    "@MAX 81\n>value():I=MAX\n",
                    base_digest=app.snapshot.digest,
                    request_id="internal-save-error",
                )
            self.assertEqual(operation.status, "error")
            self.assertEqual(operation.error, "internal_save_error")
            self.assertIn("unexpected persistence failure", operation.message)
            self.assertEqual(
                app.save_request_dict("internal-save-error")["status"],
                "error",
            )

    def test_stopped_app_rejects_new_save_without_rewriting_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            app = GlyphDiagramApp(source_path)
            initial = app.rebuild()
            app.stop()
            operation = app.submit_save(
                "@MAX 82\n>value():I=MAX\n",
                base_digest=initial.digest,
                request_id="save-after-stop",
            )
            self.assertEqual(operation.status, "error")
            self.assertEqual(operation.error, "server_stopping")
            self.assertEqual(
                source_path.read_text(encoding="utf-8"),
                INITIAL_SOURCE,
            )

    def test_startup_removes_stale_operation_temporary_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "macro.glyph"
            source_path.write_text(INITIAL_SOURCE, encoding="utf-8")
            output_dir = Path(directory) / ".glyph" / "macro"
            output_dir.mkdir(parents=True)
            stale = output_dir / ".io-state-views.json.crashed.tmp"
            stale.write_text("partial", encoding="utf-8")
            source_temporary = source_path.with_name(source_path.name + ".tmp")
            source_temporary.write_text("partial", encoding="utf-8")
            GlyphDiagramApp(source_path)
            self.assertFalse(stale.exists())
            self.assertFalse(source_temporary.exists())


if __name__ == "__main__":
    unittest.main()

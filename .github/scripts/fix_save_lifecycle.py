from pathlib import Path
import re


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing anchor: {label}")
    return text.replace(old, new, 1)


app_path = Path("glyph/diagram_app.py")
app = app_path.read_text()

app = replace_once(
    app,
    '''        self._snapshot = DiagramSnapshot(
            version=0,
            status="starting",
            source="",
            digest="",
            rendered_digest="",
            last_successful_version=0,
            operation_id=None,
            updated_at=_utc_now(),
            diagnostics=(),
            views=empty_io_state_views(),
        )
''',
    '''        self._snapshot = DiagramSnapshot(
            version=0,
            status="starting",
            source="",
            digest="",
            rendered_digest="",
            last_successful_version=0,
            operation_id=None,
            updated_at=_utc_now(),
            diagnostics=(),
            views=empty_io_state_views(),
        )
        self._cleanup_stale_temporary_files()
''',
    "startup temporary cleanup",
)

app = replace_once(
    app,
    '''    @property
    def snapshot(self) -> DiagramSnapshot:
''',
    '''    def _temporary_artifact_paths(self) -> tuple[Path, ...]:
        candidates = {
            self.input_path.with_name(self.input_path.name + ".tmp"),
            self.output_path.with_name(self.output_path.name + ".tmp"),
        }
        candidates.update(
            self.output_path.parent.glob(
                f".{self.output_path.name}.*.tmp"
            )
        )
        return tuple(candidates)

    def _cleanup_stale_temporary_files(self) -> None:
        for temporary in self._temporary_artifact_paths():
            _discard_file(temporary)

    @property
    def snapshot(self) -> DiagramSnapshot:
''',
    "temporary cleanup helpers",
)

app = replace_once(
    app,
    '''            while len(self._save_operation_order) > _MAX_SAVE_OPERATIONS:
                expired = self._save_operation_order.pop(0)
                self._save_operations.pop(expired, None)
''',
    '''            while len(self._save_operation_order) > _MAX_SAVE_OPERATIONS:
                expired_index = next(
                    (
                        index
                        for index, request_id in enumerate(
                            self._save_operation_order
                        )
                        if self._save_operations[request_id].status != "saving"
                    ),
                    None,
                )
                if expired_index is None:
                    break
                expired = self._save_operation_order.pop(expired_index)
                self._save_operations.pop(expired, None)
''',
    "operation pruning",
)

pattern = re.compile(
    r'''    def _publish_compiling\(.*?\n    def _compile_loop\(self\) -> None:\n''',
    re.DOTALL,
)
replacement = '''    def _publish_and_queue_compile(
        self,
        source: str,
        source_digest: str,
        operation_id: str,
    ) -> DiagramSnapshot:
        request = CompileRequest(operation_id, source, source_digest)
        with self._compile_condition:
            with self._lock:
                if self._stopping or self._stop.is_set():
                    raise SaveWriteError(
                        "server_stopping",
                        "Glyph Studio is stopping",
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                if (
                    self._compile_worker is None
                    or not self._compile_worker.is_alive()
                ):
                    self._compile_worker = threading.Thread(
                        target=self._compile_loop,
                        name="glyph-diagram-compile",
                        daemon=True,
                    )
                    self._compile_worker.start()
                previous = self._snapshot
                snapshot = DiagramSnapshot(
                    version=previous.version + 1,
                    status="compiling",
                    source=source,
                    digest=source_digest,
                    rendered_digest=previous.rendered_digest,
                    last_successful_version=previous.last_successful_version,
                    operation_id=operation_id,
                    updated_at=_utc_now(),
                    diagnostics=(),
                    views=previous.views,
                )
                self._snapshot = snapshot
                self._pending_compile = request
                self._compile_condition.notify_all()
                return snapshot

    def _compile_loop(self) -> None:
'''
app, count = pattern.subn(replacement, app, count=1)
if count != 1:
    raise SystemExit("missing anchor: atomic publish and queue")

app = replace_once(
    app,
    '''        snapshot = self._publish_compiling(
            source,
            source_digest,
            operation_id,
        )
        self._queue_compile(CompileRequest(operation_id, source, source_digest))
        return snapshot
''',
    '''        return self._publish_and_queue_compile(
            source,
            source_digest,
            operation_id,
        )
''',
    "rebuild queue",
)

app = replace_once(
    app,
    '''                    snapshot = self._publish_compiling(
                        source,
                        source_digest,
                        selected_request_id,
                    )
                    self._queue_compile(
                        CompileRequest(
                            selected_request_id,
                            source,
                            source_digest,
                        )
                    )
''',
    '''                    snapshot = self._publish_and_queue_compile(
                        source,
                        source_digest,
                        selected_request_id,
                    )
''',
    "save queue",
)

app = replace_once(
    app,
    '''        except SaveWriteError as exc:
            failed = replace(
                saving,
                status="error",
                http_status=int(exc.status),
                error=exc.code,
                message=str(exc),
                state=self.status_dict(),
                updated_at=_utc_now(),
            )
            self._remember_save_operation(failed)
            return failed
''',
    '''        except SaveWriteError as exc:
            failed = replace(
                saving,
                status="error",
                http_status=int(exc.status),
                error=exc.code,
                message=str(exc),
                state=self.status_dict(),
                updated_at=_utc_now(),
            )
            self._remember_save_operation(failed)
            return failed
        except Exception as exc:
            failed = replace(
                saving,
                status="error",
                http_status=int(HTTPStatus.INTERNAL_SERVER_ERROR),
                error="internal_save_error",
                message=f"{type(exc).__name__}: {exc}",
                state=self.status_dict(),
                updated_at=_utc_now(),
            )
            self._remember_save_operation(failed)
            return failed
''',
    "internal save error",
)

app = replace_once(
    app,
    '''                self.rebuild_async(source)
''',
    '''                try:
                    self.rebuild_async(source)
                except SaveWriteError:
                    if self._stop.is_set():
                        return
''',
    "watcher stopping race",
)

app = replace_once(
    app,
    '''    def stop(self) -> None:
        with self._lock:
            self._stopping = True
        self._stop.set()
        with self._compile_condition:
            self._pending_compile = None
            self._compile_condition.notify_all()
        if self._watcher is not None:
            self._watcher.join(timeout=1.0)
        if self._compile_worker is not None:
            self._compile_worker.join(timeout=1.0)
''',
    '''    def stop(self) -> None:
        with self._save_lock:
            with self._compile_condition:
                with self._lock:
                    self._stopping = True
                    self._stop.set()
                    self._pending_compile = None
                    current = self._snapshot
                    if current.status == "compiling":
                        self._snapshot = DiagramSnapshot(
                            version=current.version + 1,
                            status="error",
                            source=current.source,
                            digest=current.digest,
                            rendered_digest=current.rendered_digest,
                            last_successful_version=current.last_successful_version,
                            operation_id=current.operation_id,
                            updated_at=_utc_now(),
                            diagnostics=(
                                {
                                    "severity": "error",
                                    "code": "server_stopping",
                                    "message": "Glyph Studio stopped before compilation completed",
                                },
                            ),
                            views=current.views,
                        )
                self._compile_condition.notify_all()
        if self._watcher is not None:
            self._watcher.join(timeout=1.0)
        if self._compile_worker is not None:
            self._compile_worker.join(timeout=1.0)
        self._cleanup_stale_temporary_files()
''',
    "stop lifecycle",
)

app = replace_once(
    app,
    '''                self.end_headers()
                self.wfile.write(payload)
''',
    '''                self.end_headers()
                try:
                    self.wfile.write(payload)
                except (
                    BrokenPipeError,
                    ConnectionResetError,
                    ConnectionAbortedError,
                ):
                    pass
''',
    "diagram API broken pipe",
)
app_path.write_text(app)

desktop_path = Path("glyph/desktop_server.py")
desktop = desktop_path.read_text()
desktop = replace_once(
    desktop,
    '''            self.end_headers()
            self.wfile.write(payload)
''',
    '''            self.end_headers()
            try:
                self.wfile.write(payload)
            except (
                BrokenPipeError,
                ConnectionResetError,
                ConnectionAbortedError,
            ):
                pass
''',
    "desktop API broken pipe",
)
desktop_path.write_text(desktop)

controller_path = Path("glyph/diagram_save_controller.py")
controller = controller_path.read_text()
controller = replace_once(
    controller,
    '''#save[disabled]{cursor:wait;opacity:.72}
''',
    '''#save[data-save-pending="true"]{cursor:progress;opacity:.82}
''',
    "pending save style",
)
controller = replace_once(
    controller,
    '''  button.disabled=saveInFlight;
  button.title=t("saveTitle");
''',
    '''  button.disabled=false;
  button.dataset.savePending=saveInFlight?"true":"false";
  button.title=t("saveTitle");
''',
    "clickable save button",
)
controller_path.write_text(controller)

tests_path = Path("tests/test_macro_studio_integration.py")
tests = tests_path.read_text()
tests = replace_once(
    tests,
    '''from glyph.diagram_app import GlyphDiagramApp
''',
    '''from glyph.diagram_app import GlyphDiagramApp, SaveOperation
''',
    "SaveOperation import",
)
tests = replace_once(
    tests,
    '''            self.assertEqual(app.snapshot.status, "compiling")
            self.assertEqual(app.snapshot.rendered_digest, initial.rendered_digest)
''',
    '''            self.assertEqual(app.snapshot.status, "error")
            self.assertEqual(
                app.snapshot.diagnostics[0]["code"],
                "server_stopping",
            )
            self.assertEqual(app.snapshot.rendered_digest, initial.rendered_digest)
''',
    "stop terminal state assertion",
)
insertion = '''
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
                    "@MAX 81\\n>value():I=MAX\\n",
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
                "@MAX 82\\n>value():I=MAX\\n",
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

'''
tests = replace_once(
    tests,
    '''

if __name__ == "__main__":
''',
    insertion + '''
if __name__ == "__main__":
''',
    "new lifecycle tests",
)
tests_path.write_text(tests)

e2e_path = Path("tests/verify_save_triggered_studio.mjs")
e2e = e2e_path.read_text()
e2e = replace_once(
    e2e,
    '''  await waitForAudit(page, value => value.saveInFlight === true, "queued save did not start");
  await page.locator("#editor").fill(queuedLatest);
  await page.keyboard.press("Control+s");
''',
    '''  const queuedSaving = await waitForAudit(page, value => value.saveInFlight === true, "queued save did not start");
  assert.equal(queuedSaving.saveDisabled, false);
  await page.locator("#editor").fill(queuedLatest);
  await page.click("#save");
''',
    "button queue E2E",
)
e2e_path.write_text(e2e)

docs_path = Path("docs/STUDIO_UX.md")
docs = docs_path.read_text()
docs = replace_once(
    docs,
    '''The browser continues tracking or resubmits the same idempotent request until the operation reaches a recorded result. The editor and Save shortcut remain available; later saves are queued against the latest buffer.
''',
    '''The browser continues tracking or resubmits the same idempotent request until the operation reaches a recorded result. The editor, Save button, and Save shortcut remain available; later saves are queued against the latest buffer.
''',
    "clickable save documentation",
)
docs = replace_once(
    docs,
    '''When the application stops, it marks the server as stopping, clears pending compilation, and rejects publication from an already running operation. A late worker result cannot replace the artifact or snapshot after shutdown has started.
''',
    '''When the application stops, it serializes shutdown with source persistence, marks the server as stopping, clears pending compilation, changes an unfinished snapshot from `Compiling` to `server_stopping`, and rejects publication from an already running operation. A late worker result cannot replace the artifact or snapshot after shutdown has started. Operation-specific and fixed atomic-write temporary files are removed on shutdown and again at the next startup after an abnormal process exit.
''',
    "shutdown documentation",
)
docs_path.write_text(docs)

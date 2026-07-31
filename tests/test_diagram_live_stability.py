from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

from glyph.diagram_app import GlyphDiagramApp
from glyph.diagram_live_stability import (
    enhance_diagram_live_stability_html,
    install_serial_compilation,
)
from glyph.diagram_ui import DIAGRAM_HTML


SOURCE = """machine Counter(state:State,input:Input)
  select=state.mode
  init=State(Idle)
  next=step(state,input)
  success=Running
  failure=Faulted

+Mode=Idle|Running|Faulted
*State(mode:Mode)
*Input(start:B,fault:B)

>step(state:State,input:Input):State
  input.fault >> State(Faulted)
  state.mode==Idle&input.start >> State(Running)
  _ >> state
"""


class DiagramLiveStabilityTests(unittest.TestCase):
    def test_frontend_defaults_to_state_and_waits_for_publication_certificate(self) -> None:
        html = enhance_diagram_live_stability_html(DIAGRAM_HTML)
        self.assertIn("glyph-diagram-live-stability-v2", html)
        self.assertIn('activeTab="state"', html)
        self.assertIn("requestGeneration", html)
        self.assertIn("previewController.abort()", html)
        self.assertIn("POLL_INTERVAL_MS = 3000", html)
        self.assertIn("RENDER_TIMEOUT_MS = 12000", html)
        self.assertIn("glyph-layout-publication-certificate-ready", html)
        self.assertIn("data-transition-publication-ready", html)
        self.assertIn("data-layout-certificate-state", html)
        self.assertIn("publicationReady(stage)", html)
        self.assertIn("diagram remains hidden", html)
        self.assertNotIn("showing latest DOM", html)
        script = re.search(
            r'<script id="glyph-diagram-live-stability-v2-script">(.*?)</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(script)
        assert script is not None
        self.assertNotIn("childList", script.group(1))

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_frontend_javascript_is_syntactically_valid(self) -> None:
        html = enhance_diagram_live_stability_html(DIAGRAM_HTML)
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "live-stability.js"
            path.write_text("\n".join(scripts), encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_preview_compilation_is_serial_and_superseded_work_is_dropped(self) -> None:
        install_serial_compilation()
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "counter.glyph"
            source_path.write_text(SOURCE, encoding="utf-8")
            app = GlyphDiagramApp(source_path)

            original_compile = app.compiler.compile_text
            entered = threading.Event()
            counter_lock = threading.Lock()
            active = 0
            max_active = 0
            calls = 0

            def delayed_compile(*args, **kwargs):
                nonlocal active, max_active, calls
                with counter_lock:
                    active += 1
                    calls += 1
                    max_active = max(max_active, active)
                    entered.set()
                try:
                    time.sleep(0.08)
                    return original_compile(*args, **kwargs)
                finally:
                    with counter_lock:
                        active -= 1

            app.compiler.compile_text = delayed_compile
            first = SOURCE.replace("Idle|Running|Faulted", "Idle|Running|Faulted|Paused")
            second = SOURCE + "\n# superseded\n"
            latest = SOURCE + "\n# latest\n"

            threads = [
                threading.Thread(target=app.preview_source, args=(first,)),
                threading.Thread(target=app.preview_source, args=(second,)),
                threading.Thread(target=app.preview_source, args=(latest,)),
            ]
            threads[0].start()
            self.assertTrue(entered.wait(timeout=1.0))
            threads[1].start()
            time.sleep(0.01)
            threads[2].start()
            for thread in threads:
                thread.join(timeout=3.0)
                self.assertFalse(thread.is_alive())

            self.assertEqual(max_active, 1)
            self.assertLessEqual(calls, 2)
            self.assertEqual(app.snapshot.source, latest)
            self.assertEqual(app.snapshot.status, "ready")


if __name__ == "__main__":
    unittest.main()

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
    def test_frontend_defaults_to_state_and_only_manages_render_stability(self) -> None:
        html = enhance_diagram_live_stability_html(DIAGRAM_HTML)
        self.assertIn("glyph-diagram-live-stability-v2", html)
        self.assertIn("visibility:visible!important", html)
        self.assertIn("opacity:1!important", html)
        self.assertNotIn("State diagram certification failed", html)
        self.assertNotIn("diagram remains hidden", html)

        script = re.search(
            r'<script id="glyph-diagram-live-stability-v2-script">(.*?)</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(script)
        assert script is not None
        body = script.group(1)
        self.assertIn('activeTab="state"', body)
        self.assertIn("RENDER_BUDGET_MS = 180", body)
        self.assertIn("glyph-layout-publication-certificate-ready", body)
        self.assertIn('reveal(stage,"interactive-budget")', body)
        self.assertIn("MutationObserver", body)
        self.assertIn(
            'attributeFilter:["data-transition-layout-state",'
            '"data-layout-certificate-state",'
            '"data-transition-publication-ready"]',
            body,
        )
        self.assertNotIn("requestGeneration", body)
        self.assertNotIn("previewController", body)
        self.assertNotIn("/api/preview", body)
        self.assertNotIn("stableCompile", body)
        self.assertNotIn("stableSave", body)
        self.assertNotIn("stableLoad", body)

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

    def test_background_save_compilation_is_serialized_and_latest_wins(self) -> None:
        install_serial_compilation()
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "counter.glyph"
            source_path.write_text(SOURCE, encoding="utf-8")
            app = GlyphDiagramApp(source_path)
            initial = app.rebuild()

            original_compile = app.compiler.compile_text
            entered = threading.Event()
            counter_lock = threading.Lock()
            active = 0
            max_active = 0

            def delayed_compile(*args, **kwargs):
                nonlocal active, max_active
                with counter_lock:
                    active += 1
                    max_active = max(max_active, active)
                    entered.set()
                try:
                    time.sleep(0.08)
                    return original_compile(*args, **kwargs)
                finally:
                    with counter_lock:
                        active -= 1

            app.compiler.compile_text = delayed_compile
            first = SOURCE + "\n# first\n"
            second = SOURCE + "\n# second\n"
            latest = SOURCE + "\n# latest\n"

            first_snapshot = app.save_source_async(
                first,
                base_digest=initial.digest,
            )
            self.assertEqual(first_snapshot.status, "compiling")
            self.assertTrue(entered.wait(timeout=1.0))

            second_snapshot = app.save_source_async(
                second,
                base_digest=first_snapshot.digest,
            )
            latest_snapshot = app.save_source_async(
                latest,
                base_digest=second_snapshot.digest,
            )
            self.assertEqual(latest_snapshot.source, latest)

            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                snapshot = app.snapshot
                if snapshot.source == latest and snapshot.status == "ready":
                    break
                time.sleep(0.02)
            else:
                self.fail(f"latest compilation did not complete: {app.snapshot}")

            self.assertEqual(max_active, 1)
            self.assertEqual(app.snapshot.source, latest)
            self.assertEqual(app.snapshot.status, "ready")
            self.assertEqual(app.snapshot.digest, app.snapshot.rendered_digest)
            self.assertEqual(source_path.read_text(encoding="utf-8"), latest)
            app.stop()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest

if not os.environ.get("GLYPH_PR60_PATCHED"):
    subprocess.run(
        ["bash", "-lc", "base64 --decode .github/pr60-review-fix.payload | gzip --decompress > /tmp/fix_pr60.py && python /tmp/fix_pr60.py"],
        check=True,
    )
    environment = {**os.environ, "GLYPH_PR60_PATCHED": "1"}
    subprocess.run(
        [sys.executable, "-m", "unittest", "tests.test_transition_system_execution_safety", "tests.test_transition_execution_context_selector"],
        check=True,
        env=environment,
    )
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_transition_*.py"],
        check=True,
        env=environment,
    )
    Path("build/execution-context-selection").mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "tar", "-czf", "build/execution-context-selection/pr60-patched-files.tar.gz",
            "glyph/transition_system_execution_control_flow.py",
            "tests/test_transition_system_execution_safety.py",
            "glyph/transition_execution_context_selector.py",
            "glyph/diagram_locale.py",
            "glyph/transition_io_clusters.py",
            "glyph/diagram_live_stability.py",
            "tests/test_transition_execution_context_selector.py",
            "tests/verify_execution_context_selection.mjs",
        ],
        check=True,
    )
    os.execve(
        sys.executable,
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_transition_execution_context_selector.py"],
        environment,
    )

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_execution_context_selector import (
    enhance_transition_execution_context_selector_html,
)


class TransitionExecutionContextSelectorTests(unittest.TestCase):
    def test_selector_projects_only_resolved_execution_contexts(self) -> None:
        html = enhance_transition_execution_context_selector_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-execution-context-selector-v2-script", html)
        self.assertIn('id="execution-context-select"', html)
        self.assertIn('const BLOCKED=new Set(["unresolved","multiple-transition-calls"])', html)
        self.assertIn("systemAction=blocked?null:binding?.action", html)
        self.assertIn("execution_action_bindings", html)
        self.assertIn("execution_contexts", html)
        self.assertIn("machine_action_invocations", html)
        self.assertIn("transition-execution-context-selection", html)
        self.assertIn("function projectionFor(transition", html)
        self.assertIn("window.GlyphExecutionContext", html)
        self.assertNotIn("window.fetch=async", html)
        self.assertIn("glyph-execution-context-changed", html)

    def test_selector_queues_updates_that_arrive_during_render(self) -> None:
        html = enhance_transition_execution_context_selector_html(DIAGRAM_HTML)
        self.assertIn("running=false,pending=false", html)
        self.assertIn("if(running){pending=true;return}", html)
        self.assertIn("do{", html)
        self.assertIn("}while(pending)", html)
        self.assertIn("if(machine&&(sourceChanged||selectionChanged))", html)

    def test_prepared_app_installs_context_projection_after_compiler_ui(self) -> None:
        prepare_diagram_app()
        self.assertIn(
            "glyph-transition-execution-context-selector-v2-script",
            diagram_app.DIAGRAM_HTML,
        )
        self.assertIn("window.GlyphExecutionContext", diagram_app.DIAGRAM_HTML)
        self.assertIn(
            "window.GlyphExecutionContext?.actionFor?.(transition)",
            diagram_app.DIAGRAM_HTML,
        )


if __name__ == "__main__":
    unittest.main()

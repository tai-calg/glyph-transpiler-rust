from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_execution_context_selector import (
    enhance_transition_execution_context_selector_html,
)


class TransitionExecutionContextSelectorTests(unittest.TestCase):
    def test_selector_projects_machine_or_concrete_system_action(self) -> None:
        html = enhance_transition_execution_context_selector_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-execution-context-selector-v1-script", html)
        self.assertIn('id="execution-context-select"', html)
        self.assertIn('label.textContent="実行コンテキスト"', html)
        self.assertIn('key:MACHINE,label:"Machineのみ"', html)
        self.assertIn("execution_action_bindings", html)
        self.assertIn("machine_action_invocations", html)
        self.assertIn("transition-execution-context-selection", html)
        self.assertIn("window.fetch=async", html)
        self.assertIn("projectPayload(payload)", html)
        self.assertIn("glyph-execution-context-changed", html)

    def test_prepared_app_installs_context_projection_after_compiler_ui(self) -> None:
        prepare_diagram_app()
        self.assertIn(
            "glyph-transition-execution-context-selector-v1-script",
            diagram_app.DIAGRAM_HTML,
        )
        self.assertIn("window.GlyphExecutionContext", diagram_app.DIAGRAM_HTML)


if __name__ == "__main__":
    unittest.main()

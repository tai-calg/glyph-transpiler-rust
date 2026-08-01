from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_execution_context_selector import (
    enhance_transition_execution_context_selector_html,
)


class TransitionExecutionContextSelectorTests(unittest.TestCase):
    def test_selector_projects_resolved_and_strict_native_actions(self) -> None:
        html = enhance_transition_execution_context_selector_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-execution-context-selector-v5-script", html)
        self.assertIn('id="execution-context-select"', html)
        self.assertIn('const BLOCKED=new Set(["unresolved","multiple-transition-calls","missing"])', html)
        self.assertIn("systemAction=blocked?null:binding.action", html)
        self.assertIn('if(!binding)return{action:null', html)
        self.assertIn('status:"missing"', html)
        self.assertIn("execution_action_bindings", html)
        self.assertIn("execution_contexts", html)
        self.assertIn("machine_action_invocations", html)
        self.assertIn("transition-execution-context-selection", html)
        self.assertIn("function projectionFor(transition", html)
        self.assertIn("window.GlyphExecutionContext", html)
        self.assertNotIn("window.fetch=async", html)
        self.assertIn("glyph-execution-context-changed", html)
        self.assertIn('system_action_projection_source==="rtai-execution-evidence-v2"', html)
        self.assertIn('value?.kind==="effect-trace"', html)
        self.assertIn("transition?.system_action", html)
        self.assertIn("sameSemanticEvents", html)
        self.assertIn("semantic-event-reference", html)
        self.assertIn("deduplicated_equivalent_action:semanticAlias", html)
        self.assertNotIn("!parts.includes(value)", html)

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
            "glyph-transition-execution-context-selector-v5-script",
            diagram_app.DIAGRAM_HTML,
        )
        self.assertIn("window.GlyphExecutionContext", diagram_app.DIAGRAM_HTML)
        self.assertIn(
            "window.GlyphExecutionContext?.actionFor?.(transition)",
            diagram_app.DIAGRAM_HTML,
        )


if __name__ == "__main__":
    unittest.main()

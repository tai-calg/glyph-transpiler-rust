from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_semantic_role_lines import (
    enhance_transition_semantic_role_lines_html,
)


class TransitionSemanticRoleLineTests(unittest.TestCase):
    def test_legacy_enhancer_splits_roles_without_character_breaking(self) -> None:
        html = enhance_transition_semantic_role_lines_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-semantic-role-lines-v1-script", html)
        self.assertIn("transition-role-line", html)
        self.assertIn("return value.length", html)
        self.assertIn("word-break:normal", html)
        self.assertIn("overflow-wrap:normal", html)
        self.assertIn("transitionSemanticRoleLinesReady", html)
        self.assertIn("glyphTransitionIoCollisionSolver?.run", html)

    def test_interactive_app_excludes_collision_solver_role_lines(self) -> None:
        prepare_diagram_app()
        html = diagram_app.DIAGRAM_HTML
        self.assertNotIn("glyph-transition-semantic-role-lines-v1-script", html)
        self.assertNotIn("window.glyphTransitionSemanticRoleLines", html)
        self.assertIn("glyph-transition-readable-layout-v1-script", html)
        self.assertIn("glyph-transition-readable-exports-v1-script", html)


if __name__ == "__main__":
    unittest.main()

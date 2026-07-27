from __future__ import annotations

import unittest

from glyph import diagram_app
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_semantic_role_lines import (
    enhance_transition_semantic_role_lines_html,
)


class TransitionSemanticRoleLineTests(unittest.TestCase):
    def test_enhancer_splits_roles_without_character_breaking(self) -> None:
        html = enhance_transition_semantic_role_lines_html(DIAGRAM_HTML)
        self.assertIn("glyph-transition-semantic-role-lines-v1-script", html)
        self.assertIn("transition-role-line", html)
        self.assertIn("return value.length", html)
        self.assertIn("word-break:normal", html)
        self.assertIn("overflow-wrap:normal", html)
        self.assertIn("transitionSemanticRoleLinesReady", html)
        self.assertIn("glyphTransitionIoCollisionSolver?.run", html)

    def test_prepared_app_installs_role_lines_last(self) -> None:
        prepare_diagram_app()
        html = diagram_app.DIAGRAM_HTML
        role_lines = html.index("glyph-transition-semantic-role-lines-v1-script")
        readable_layout = html.index("glyph-transition-readable-layout-v1-script")
        exports = html.index("glyph-transition-readable-exports-v1-script")
        self.assertGreater(role_lines, readable_layout)
        self.assertGreater(role_lines, exports)
        self.assertIn("window.glyphTransitionSemanticRoleLines", html)


if __name__ == "__main__":
    unittest.main()

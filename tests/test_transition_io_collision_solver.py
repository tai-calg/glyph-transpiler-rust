from __future__ import annotations

import unittest

from glyph.diagram_ui import DIAGRAM_HTML
from glyph.transition_io_collision_solver import enhance_transition_io_collision_solver_html


class TransitionIoCollisionSolverTests(unittest.TestCase):
    def test_solver_owns_geometry_but_not_pointer_interaction(self) -> None:
        html = enhance_transition_io_collision_solver_html(DIAGRAM_HTML)

        self.assertIn("glyph-transition-io-collision-solver-v1-script", html)
        self.assertIn("function solve(entries,index,placed,assignment,deadline)", html)
        self.assertIn("MAX_DISTANCE=96", html)
        self.assertIn("transitionIoCollisionSolved", html)
        self.assertNotIn("manualPointer", html)
        self.assertNotIn('cluster.dataset.manualIo="true"', html)
        self.assertNotIn('event.target?.closest?.(".transition-io-cluster")', html)
        self.assertNotIn('addEventListener("pointerdown"', html)

    def test_enhancer_is_idempotent(self) -> None:
        once = enhance_transition_io_collision_solver_html(DIAGRAM_HTML)
        twice = enhance_transition_io_collision_solver_html(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()

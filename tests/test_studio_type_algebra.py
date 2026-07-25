from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from glyph.studio import GlyphStudio, STUDIO_HTML


MACHINE_SOURCE = """
resource Token[Ready]
+Mode=Idle|Running|Stopped|Faulted
+Command=Stop|Run(U)
+Error=Bad
*Input(tick:B)
*System(mode:Mode,count:U,command:Command)

>step(state:System,input:Input):System|Error
  state.mode==Idle >> Ok(System(Running,state.count+1,Run(1)))
  state.mode==Running >> Ok(System(Stopped,state.count+1,Stop))
  _ >> Ok(state)

machine Controller(state:System,input:Input)
  select=state.mode
  init=System(Idle,0,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted
""".lstrip()


class StudioTypeAlgebraTests(unittest.TestCase):
    def test_studio_html_contains_type_algebra_view(self) -> None:
        self.assertIn("Type Algebra", STUDIO_HTML)
        self.assertIn("function typeAlgebraView()", STUDIO_HTML)
        self.assertIn("Machine selector × input coverage", STUDIO_HTML)
        self.assertIn("Machine init reachability", STUDIO_HTML)

    def test_successful_build_surfaces_type_algebra_warning(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyph-studio-type-algebra-") as directory:
            source_path = Path(directory) / "design.glyph"
            source_path.write_text(
                "*Impossible(value:Never)\n",
                encoding="utf-8",
            )
            snapshot = GlyphStudio(source_path).rebuild()

            self.assertEqual(snapshot.status, "ready")
            self.assertTrue(
                any(
                    item.get("code") == "type-algebra-impossible"
                    and item.get("subject") == "Impossible"
                    for item in snapshot.diagnostics
                )
            )
            view = snapshot.glyph04_views["type_algebra"]
            impossible = next(item for item in view["types"] if item["name"] == "Impossible")
            self.assertTrue(impossible["impossible"])
            self.assertIn("type-algebra-tooling.json", snapshot.artifacts)

    def test_machine_coverage_and_state_graph_are_projected_from_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyph-studio-machine-coverage-") as directory:
            source_path = Path(directory) / "controller.glyph"
            source_path.write_text(MACHINE_SOURCE, encoding="utf-8")
            snapshot = GlyphStudio(source_path).rebuild()

            self.assertEqual(snapshot.status, "ready")
            payload = json.loads(snapshot.artifacts["type-algebra-tooling.json"])
            coverage = payload["machine_coverage"]
            self.assertEqual(len(coverage), 1)
            self.assertEqual(coverage[0]["machine"], "Controller")
            self.assertIsNotNone(coverage[0]["possible_pairs"])
            state_graphs = payload["machine_state_reachability"]
            self.assertEqual(len(state_graphs), 1)
            self.assertEqual(state_graphs[0]["initial_state"], "Idle")
            self.assertEqual(state_graphs[0]["definitely_unreachable"], ["Faulted"])

            projected = snapshot.glyph04_views["type_algebra"]
            self.assertEqual(projected["machine_coverage"], coverage)
            self.assertEqual(
                projected["machine_state_reachability"],
                state_graphs,
            )
            self.assertEqual(
                snapshot.glyph04_views["summary"]["type_algebra_machines"],
                1,
            )
            self.assertEqual(
                snapshot.glyph04_views["summary"]["type_algebra_unreachable_states"],
                1,
            )
            self.assertTrue(
                any(
                    item.get("code") == "machine-state-unreachable"
                    for item in snapshot.diagnostics
                )
            )


if __name__ == "__main__":
    unittest.main()

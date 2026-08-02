from __future__ import annotations

import unittest

from glyph import parse_compilation_model


class SystemOpaqueBoundaryTests(unittest.TestCase):
    def test_opaque_rust_function_is_internal_not_sink(self) -> None:
        source = """
system BatchRuntime
  entry run
  sink submit_batch

*Input(value:U)
*Layout(value:U)
*Receipt(value:U)

~layout_lane(input:Input):Layout
!submit_batch(layout:Layout):Receipt

>run(input:Input):Receipt
  layout := layout_lane(input)
  submit_batch(layout)
"""
        model = parse_compilation_model(source, "batch.glyph")
        system = model.architecture.systems[0]
        components = {component.name: component for component in system.components}

        self.assertEqual(system.sinks, ("submit_batch",))
        self.assertEqual(components["run"].role, "entry")
        self.assertEqual(components["layout_lane"].role, "internal")
        self.assertEqual(components["layout_lane"].kind, "rust")
        self.assertEqual(components["submit_batch"].role, "sink")
        self.assertEqual(components["submit_batch"].kind, "effect")

        names = {component.id: component.name for component in system.components}
        edges = {
            (names[edge.source_id], names[edge.target_id], edge.kind)
            for edge in system.edges
        }
        self.assertEqual(
            edges,
            {
                ("run", "layout_lane", "call"),
                ("run", "submit_batch", "call"),
            },
        )

    def test_reachable_effect_still_requires_sink_declaration(self) -> None:
        source = """
system BatchRuntime
  entry run

*Input(value:U)
*Layout(value:U)
*Receipt(value:U)

~layout_lane(input:Input):Layout
!submit_batch(layout:Layout):Receipt
>run(input:Input):Receipt=submit_batch(layout_lane(input))
"""
        with self.assertRaisesRegex(Exception, "sinkとして宣言していない"):
            parse_compilation_model(source, "batch.glyph")


if __name__ == "__main__":
    unittest.main()

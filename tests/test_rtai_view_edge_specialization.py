from __future__ import annotations

from pathlib import Path
import unittest

from glyph.compilation import CompilationPipeline
from glyph.state_machine_analysis import analyze_machine
from glyph.transition_analysis.machine_relation import build_machine_relation
from glyph.transition_analysis.view_edge_specialization import (
    ViewEdgeBindingStatus,
    attach_view_edge_specialization,
    specialize_view_edges,
)


ROOT = Path(__file__).resolve().parents[1]

SOURCE = """machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*Input(open_request:B)
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request >> DoorState(Open)
  _ >> state
"""


class ViewEdgeSpecializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = CompilationPipeline().compile_text(
            SOURCE,
            source_name="view-edge-specialization.glyph",
        ).model
        relation = build_machine_relation(cls.model, "Door")
        assert relation is not None
        cls.open_edge, cls.same_edge = relation.edges
        cls.machine = {
            "name": "Door",
            "analysis": {},
            "transitions": [
                {
                    "id": "T1",
                    "source_state": "Closed",
                    "target_state": "Open",
                    "source": {"line": cls.open_edge.source_line},
                    "synthesized_failure": False,
                },
                {
                    "id": "T2",
                    "source_state": "Open",
                    "target_state": "Open",
                    "source": {"line": cls.same_edge.source_line},
                    "synthesized_failure": False,
                },
                {
                    "id": "T3",
                    "source_state": "Closed",
                    "target_state": "Alarm",
                    "source": {"line": cls.open_edge.source_line},
                    "synthesized_failure": True,
                },
                {
                    "id": "T4",
                    "source_state": "Alarm",
                    "target_state": "Open",
                    "source": {"line": 9999},
                    "synthesized_failure": False,
                },
            ],
        }

    def test_exact_same_state_and_synthesized_failure_bindings(self) -> None:
        bindings = specialize_view_edges(self.model, self.machine)
        self.assertEqual(
            [item.status for item in bindings],
            [
                ViewEdgeBindingStatus.EXACT,
                ViewEdgeBindingStatus.EXACT,
                ViewEdgeBindingStatus.SYNTHESIZED_FAILURE,
                ViewEdgeBindingStatus.UNMAPPED,
            ],
        )
        self.assertEqual(bindings[0].relation_edge_id, self.open_edge.edge_id)
        self.assertEqual(bindings[1].relation_edge_id, self.same_edge.edge_id)
        self.assertEqual(bindings[2].relation_edge_id, self.open_edge.edge_id)

    def test_attachment_keeps_unmapped_edges_explicit(self) -> None:
        result = attach_view_edge_specialization(self.model, self.machine)
        self.assertEqual(
            result["analysis"]["rtai_view_edge_exact_binding_count"],
            3,
        )
        self.assertEqual(
            result["analysis"]["rtai_view_edge_unmapped_count"],
            1,
        )
        self.assertEqual(
            result["transitions"][3]["rtai_view_edge_specialization"]["status"],
            "unmapped",
        )

    def test_function_block_generated_lines_bind_to_original_machine_edges(self) -> None:
        path = ROOT / "examples/acceptance/motor_safety.glyph"
        compiled = CompilationPipeline().compile_text(
            path.read_text(encoding="utf-8"),
            source_name=str(path),
        )
        machine_view = analyze_machine(
            compiled.model,
            compiled.diagrams.ir.machines[0],
        )
        relation = build_machine_relation(compiled.model, "Motor")
        assert relation is not None
        bindings = specialize_view_edges(compiled.model, machine_view)
        self.assertTrue(bindings)
        self.assertTrue(
            all(item.status is ViewEdgeBindingStatus.EXACT for item in bindings),
            {
                "bindings": [item.to_ir() for item in bindings],
                "relation": relation.to_ir(),
                "transition_lines": [
                    item.get("source") for item in machine_view["transitions"]
                ],
            },
        )
        self.assertTrue(all(item.relation_edge_id for item in bindings))
        self.assertTrue(all(item.source_line > 0 for item in bindings))


if __name__ == "__main__":
    unittest.main()

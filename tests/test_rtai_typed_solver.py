from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.compiler import TypeRef, parse_expr
from glyph.transition_analysis.preimage import (
    PreimageStatus,
    compute_transition_call_preimage,
)
from glyph.transition_analysis.typed_smt import (
    SatModel,
    SolverUnknown,
    TypedConstraintSolver,
    UnsatProven,
)


SOURCE = """machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*Input(open_request:B,authorized:B)
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request&input.authorized >> DoorState(Open)
  state.mode==Closed&input.open_request >> DoorState(Alarm)
  _ >> state

>control(state:DoorState,input:Input):DoorState=step(state,input)
"""


class TypedSolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = CompilationPipeline().compile_text(
            SOURCE,
            source_name="typed-solver.glyph",
        ).model
        cls.solver = TypedConstraintSolver(cls.model)
        cls.types = {
            "state": TypeRef("DoorState"),
            "input": TypeRef("Input"),
        }

    def test_unsat_is_proven_only_by_complete_finite_enumeration(self) -> None:
        result = self.solver.solve(
            parse_expr("input.open_request&!input.open_request"),
            self.types,
        )
        self.assertIsInstance(result, UnsatProven)
        self.assertIn("exhaustive typed finite-domain", result.certificate)

    def test_sat_returns_a_concrete_typed_model(self) -> None:
        result = self.solver.solve(
            parse_expr("state.mode==Closed&input.open_request"),
            self.types,
        )
        self.assertIsInstance(result, SatModel)
        assert isinstance(result, SatModel)
        self.assertEqual(set(result.mapping), {"input", "state"})

    def test_unbounded_domain_is_unknown_not_unsat(self) -> None:
        result = self.solver.solve(
            parse_expr("count>0"),
            {"count": TypeRef("I")},
        )
        self.assertIsInstance(result, SolverUnknown)

    def test_preimage_publishes_solver_outcomes(self) -> None:
        preimage = compute_transition_call_preimage(
            self.model,
            "Door",
            (parse_expr("state"), parse_expr("input")),
            type_environment=self.types,
        )
        self.assertIsNotNone(preimage)
        assert preimage is not None
        self.assertEqual(len(preimage.edges), 3)
        self.assertTrue(
            all(edge.status is PreimageStatus.SAT_MODEL for edge in preimage.edges)
        )
        self.assertTrue(
            all(edge.solver_result.to_ir()["outcome"] == "sat-model" for edge in preimage.edges)
        )

    def test_contradictory_caller_path_removes_every_edge(self) -> None:
        preimage = compute_transition_call_preimage(
            self.model,
            "Door",
            (parse_expr("state"), parse_expr("input")),
            caller_condition=parse_expr("input.open_request&!input.open_request"),
            type_environment=self.types,
        )
        self.assertIsNotNone(preimage)
        assert preimage is not None
        self.assertTrue(
            all(edge.status is PreimageStatus.PROVEN_FALSE for edge in preimage.edges)
        )
        self.assertTrue(
            all(edge.solver_result.to_ir()["outcome"] == "unsat-proven" for edge in preimage.edges)
        )


if __name__ == "__main__":
    unittest.main()

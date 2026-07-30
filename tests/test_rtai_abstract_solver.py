from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.compiler import BinaryExpr, NameExpr, NumberExpr
from glyph.transition_analysis.abstract_solver import AbstractInterpreter
from glyph.transition_analysis.abstract_state import AnalysisBudget
from glyph.transition_analysis.effect_summary import identity_effect_summary
from glyph.transition_analysis.exactness import (
    Approximation,
    ApproximationKind,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)
from glyph.transition_analysis.teir import Assign, BasicBlock, Function, Jump


SOURCE = """system DoorControl
  entry control

  in state:DoorState
  in input:Input
  out state_out:DoorState

  state -> control
  input -> control
  control -> state_out
  control -> actuator

machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*Input(open_request:B,authorized:B)
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)

!actuator(state:DoorState):DoorState

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request&input.authorized >> DoorState(Open)
  state.mode==Closed&input.open_request >> DoorState(Alarm)
  _ >> state

>control(state:DoorState,input:Input):DoorState
  next := step(state,input)
  observed := actuator(next)
  observed
"""


def compile_model(source: str, name: str):
    return CompilationPipeline().compile_text(source, source_name=name).model


def exact_effect() -> Approximation:
    return Approximation.exact(
        ExactnessProof(
            ExactnessProofKind.STRUCTURAL_IDENTITY,
            ExactnessProofScope.EFFECT_TRACE,
            "verified read-only identity actuator",
        )
    )


class GuardedAbstractExecutionTests(unittest.TestCase):
    def test_machine_edges_keep_correlated_effect_traces(self) -> None:
        model = compile_model(SOURCE, "abstract-door.glyph")
        analyzer = AbstractInterpreter(
            model,
            effect_summaries={
                "actuator": identity_effect_summary(
                    "actuator",
                    "state",
                    approximation=exact_effect(),
                )
            },
        )
        result = analyzer.analyze("control")
        returned = [
            item
            for item in result.completed
            if item.completion == frozenset({"returned"})
        ]
        self.assertEqual(len(returned), 3)
        self.assertTrue(all(len(item.transition_trace) == 1 for item in returned))
        self.assertTrue(all(len(item.effect_trace) == 1 for item in returned))
        self.assertEqual(
            {item.transition_trace[0].edge_id.rsplit(":", 1)[-1] for item in returned},
            {"0", "1", "2"},
        )
        for item in returned:
            self.assertEqual(
                item.transition_trace[0].result,
                item.effect_trace[0].arguments[0],
            )
            self.assertFalse(item.transition_trace_top)
            self.assertFalse(item.effect_trace_top)

    def test_unknown_effect_is_not_promoted_to_exact(self) -> None:
        model = compile_model(SOURCE, "abstract-unknown-effect.glyph")
        result = AbstractInterpreter(model).analyze("control")
        self.assertEqual(result.approximation.kind, ApproximationKind.UNKNOWN)
        self.assertIn("unknown-effect-result", result.approximation.causes)
        self.assertIn("unknown-effect-footprint", result.approximation.causes)
        self.assertTrue(
            any("propagated-failure" in item.completion for item in result.completed)
        )

    def test_loop_budget_returns_top_trace_instead_of_dropping_execution(self) -> None:
        model = compile_model(SOURCE, "abstract-loop.glyph")
        analyzer = AbstractInterpreter(
            model,
            budget=AnalysisBudget(
                max_steps=64,
                max_alternatives_per_block=4,
                max_block_iterations=2,
                max_phi_values=4,
            ),
        )
        original = analyzer.functions["control"]
        loop = Function(
            "control",
            original.parameters,
            original.return_type,
            "loop",
            (
                BasicBlock(
                    "loop",
                    (
                        Assign(
                            "state",
                            BinaryExpr("+", NameExpr("state"), NumberExpr("1")),
                            original.source_line,
                        ),
                    ),
                    Jump("loop"),
                ),
            ),
            original.source_line,
        )
        analyzer.functions["control"] = loop
        result = analyzer.analyze("control")
        self.assertEqual(result.approximation.kind, ApproximationKind.UNKNOWN)
        self.assertTrue(
            any("block-fixpoint-budget" in item.unknown_reasons for item in result.completed)
        )
        self.assertTrue(any(item.transition_trace_top for item in result.completed))
        self.assertTrue(any(item.effect_trace_top for item in result.completed))


if __name__ == "__main__":
    unittest.main()

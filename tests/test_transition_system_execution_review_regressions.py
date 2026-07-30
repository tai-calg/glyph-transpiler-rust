from __future__ import annotations

import unittest
from typing import Mapping

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views


def compile_source(source: str) -> dict[str, object]:
    output = CompilationPipeline().compile_text(source, source_name="review-regression.glyph")
    return build_io_state_views(output.model, output.diagrams.ir)


def opening_transition(views: Mapping[str, object]) -> Mapping[str, object]:
    machine = views["state"]["machines"][0]
    return next(
        item
        for item in machine["transitions"]
        if item["source_state"] == "Closed" and item["target_state"] == "Open"
    )


BASE = """machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*Input(open_request,authorized:B)
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)
*Receipt(state:DoorState)

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request >> DoorState(Open)
  _ >> state
"""


SYSTEM = """system DoorControl
  entry control
  in state:DoorState
  in input:Input
  out receipt:Receipt
  state -> control
  input -> control
  control -> receipt
  control -> actuator
  control -> audit
"""


class TransitionSystemExecutionReviewRegressions(unittest.TestCase):
    def test_repeated_guard_does_not_publish_an_infeasible_action_case(self) -> None:
        source = SYSTEM + "\n" + BASE + """
!actuator(state:DoorState):Receipt
!audit(state:DoorState):Receipt

>control(state:DoorState,input:Input):Receipt
  input.authorized >> actuator(step(state,input))
  input.authorized >> audit(step(state,input))
  _ >> actuator(step(state,input))
"""
        transition = opening_transition(compile_source(source))
        context = transition["execution_contexts"][0]
        expressions = [
            invocation["expression"]
            for case in context["action_cases"]
            for invocation in case["action_invocations"]
        ]
        self.assertFalse(any(expression.startswith("audit(") for expression in expressions))
        self.assertEqual(len(context["action_cases"]), 2)
        conditions = {case["condition"] for case in context["action_cases"]}
        self.assertIn("input.authorized", conditions)
        self.assertIn("!(input.authorized)", conditions)

    def test_try_success_binding_uses_unwrapped_value_without_replaying_operation(self) -> None:
        source = SYSTEM + "\n" + BASE + """
+AuditError=Rejected
!audit(state:DoorState):R<B,AuditError>
!apply_checked(checked:B,state:DoorState):R<Receipt,AuditError>

>control(state:DoorState,input:Input):R<Receipt,AuditError>
  next := step(state,input)
  checked := audit(next)?
  apply_checked(checked,next)
"""
        transition = opening_transition(compile_source(source))
        context = transition["execution_contexts"][0]
        success = next(
            case for case in context["action_cases"] if case["reaches_continuation"]
        )
        failure = next(
            case for case in context["action_cases"] if not case["reaches_continuation"]
        )
        success_expressions = [
            invocation["expression"] for invocation in success["action_invocations"]
        ]
        self.assertEqual(success_expressions[0], "audit(DoorState(Open))")
        self.assertEqual(sum(item.startswith("audit(") for item in success_expressions), 1)
        self.assertIn(
            "__glyph_success_value__(audit(DoorState(Open)))",
            success_expressions[1],
        )
        self.assertNotIn("audit(DoorState(Open))?", success_expressions[1])
        self.assertEqual(
            [invocation["expression"] for invocation in failure["action_invocations"]],
            ["audit(DoorState(Open))"],
        )
        self.assertEqual(failure["outcome"], "failure-return")


if __name__ == "__main__":
    unittest.main()

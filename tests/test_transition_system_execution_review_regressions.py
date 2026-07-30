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


def action_display(context: Mapping[str, object]) -> str:
    action = context.get("action")
    return str(action.get("display") or "") if isinstance(action, Mapping) else ""


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

    def test_system_guard_is_specialized_by_transition_source_state(self) -> None:
        source = SYSTEM + "\n" + BASE + """
!actuator(state:DoorState):Receipt
!audit(state:DoorState):Receipt

>control(state:DoorState,input:Input):Receipt
  state.mode==Closed >> actuator(step(state,input))
  _ >> audit(step(state,input))
"""
        views = compile_source(source)
        machine = views["state"]["machines"][0]
        closed_open = next(
            item
            for item in machine["transitions"]
            if item["source_state"] == "Closed" and item["target_state"] == "Open"
        )
        open_open = next(
            item
            for item in machine["transitions"]
            if item["source_state"] == "Open" and item["target_state"] == "Open"
        )
        closed_context = closed_open["execution_contexts"][0]
        open_context = open_open["execution_contexts"][0]
        self.assertEqual(closed_context["status"], "resolved")
        self.assertEqual(open_context["status"], "resolved")
        self.assertEqual(
            action_display(closed_context),
            "actuator(DoorState(Open))",
        )
        self.assertEqual(
            action_display(open_context),
            "audit(DoorState(Open))",
        )
        self.assertEqual(len(closed_context["action_cases"]), 1)
        self.assertEqual(len(open_context["action_cases"]), 1)

    def test_try_success_binding_uses_unwrapped_value_without_replaying_operation(self) -> None:
        system = SYSTEM.replace("  control -> actuator\n", "  control -> apply_checked\n")
        source = system + "\n" + BASE + """
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
        self.assertEqual(
            success_expressions,
            [
                "audit(DoorState(Open))",
                "apply_checked(checked,DoorState(Open))",
            ],
        )
        self.assertEqual(sum(item.startswith("audit(") for item in success_expressions), 1)
        self.assertFalse(any("__glyph_success_value__" in item for item in success_expressions))
        self.assertFalse(any("audit(DoorState(Open))?" in item for item in success_expressions))
        self.assertEqual(
            [invocation["expression"] for invocation in failure["action_invocations"]],
            ["audit(DoorState(Open))"],
        )
        self.assertEqual(failure["outcome"], "failure-return")


    def test_auto_projection_requires_every_machine_context(self) -> None:
        source = """system DoorControl
  entry control
  in state:DoorState
  in input:Input
  out receipt:Receipt
  state -> control
  input -> control
  control -> receipt
  control -> actuator

system DoorAudit
  entry audit_control
  in state:DoorState
  in input:Input
  out receipt:Receipt
  state -> audit_control
  input -> audit_control
  audit_control -> receipt
  audit_control -> audit

machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*Input(open_request:B)
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)
*Receipt(state:DoorState)

!actuator(state:DoorState):Receipt
!audit(state:DoorState):Receipt

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request >> DoorState(Open)
  _ >> state

>control(state:DoorState,input:Input):Receipt
  state.mode==Closed >> actuator(step(state,input))
  _ >> Receipt(state)

>audit_control(state:DoorState,input:Input):Receipt
  state.mode==Open >> audit(step(state,input))
  _ >> Receipt(state)
"""
        transition = opening_transition(compile_source(source))
        self.assertEqual(
            {item.get("system") for item in transition["execution_contexts"]},
            {"DoorControl"},
        )
        self.assertIsNone(transition.get("display_action"))
        self.assertTrue(transition["action_scope"]["context_required"])
        self.assertEqual(
            transition["action_scope"]["missing_execution_context_count"],
            1,
        )

    def test_transition_call_inside_guard_condition_is_blocked(self) -> None:
        system = SYSTEM.replace("  control -> audit\n", "")
        source = system + "\n" + BASE + """
!actuator(state:DoorState):Receipt

>is_open(state:DoorState):B=state.mode==Open

>control(state:DoorState,input:Input):Receipt
  is_open(step(state,input)) >> actuator(step(state,input))
  _ >> Receipt(state)
"""
        transition = opening_transition(compile_source(source))
        context = transition["execution_contexts"][0]
        self.assertEqual(context["status"], "unresolved")
        self.assertIsNone(context["action"])
        self.assertFalse(context["action_invocations"])

    def test_multiple_external_machine_inputs_cannot_be_swapped(self) -> None:
        source = """ext event():Signal
ext mode():Signal

system DoorControl
  entry control
  in state:DoorState
  in event:Signal
  in mode:Signal
  out state_out:DoorState
  state -> control
  event -> control
  mode -> control
  control -> state_out
  control -> actuator

machine Door(state:DoorState,event:Signal,mode:Signal)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,event,mode)
  success=Open
  failure=Alarm

+Signal=Active|Inactive
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)

!actuator(state:DoorState):DoorState

>step(state:DoorState,event:Signal,mode:Signal):DoorState
  state.mode==Closed&event==Active >> DoorState(Open)
  state.mode==Closed&mode==Active >> DoorState(Alarm)
  _ >> state

>control(state:DoorState):DoorState
  next := step(state,mode(),event())
  actuator(next)
"""
        views = compile_source(source)
        machine = views["state"]["machines"][0]
        self.assertTrue(
            any(
                item.get("code") == "STIR_SYSTEM_TRANSITION_ARGUMENT_UNPROVEN"
                for item in machine["diagnostics"]
            )
        )
        contexts = [
            context
            for transition in machine["transitions"]
            for context in transition.get("execution_contexts", [])
        ]
        self.assertTrue(contexts)
        self.assertTrue(all(context["status"] == "unresolved" for context in contexts))
        self.assertTrue(all(context.get("action") is None for context in contexts))


if __name__ == "__main__":
    unittest.main()

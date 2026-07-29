from __future__ import annotations

import unittest
from typing import Mapping

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views


def compile_source(source: str) -> dict[str, object]:
    output = CompilationPipeline().compile_text(source, source_name="control-flow.glyph")
    return build_io_state_views(output.model, output.diagrams.ir)


def display(value: object) -> str:
    return str(value.get("display") or "") if isinstance(value, Mapping) else ""


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

*Input(open_request:B)
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)
*Receipt(state:DoorState)

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request >> DoorState(Open)
  _ >> state
"""


class TransitionSystemExecutionControlFlowTests(unittest.TestCase):
    def test_actionless_context_is_preserved_and_blocks_automatic_projection(self) -> None:
        source = """system DoorControl
  entry control
  in state:DoorState
  in input:Input
  out receipt:Receipt
  state -> control
  input -> control
  control -> receipt
  control -> actuator

system DoorObserve
  entry observe
  in state:DoorState
  in input:Input
  out state_out:DoorState
  state -> observe
  input -> observe
  observe -> state_out

""" + BASE + """
!actuator(state:DoorState):Receipt

>control(state:DoorState,input:Input):Receipt
  next := step(state,input)
  actuator(next)

>observe(state:DoorState,input:Input):DoorState
  next := step(state,input)
  next
"""
        transition = opening_transition(compile_source(source))
        bindings = {
            item["system"]: item
            for item in transition["execution_action_bindings"]
        }
        self.assertEqual(set(bindings), {"DoorControl", "DoorObserve"})
        self.assertEqual(display(bindings["DoorControl"]["action"]), "actuator(DoorState(Open))")
        self.assertIsNone(bindings["DoorObserve"]["action"])
        self.assertEqual(bindings["DoorObserve"]["status"], "resolved")
        self.assertTrue(transition["action_scope"]["context_required"])
        self.assertIsNone(transition["display_action"])

    def test_unresolved_context_is_preserved_and_blocks_other_context_auto_projection(self) -> None:
        source = """system DoorControl
  entry control
  in state:DoorState
  in input:Input
  out receipt:Receipt
  state -> control
  input -> control
  control -> receipt
  control -> actuator

system DoorUnknown
  entry unknown
  in state:DoorState
  in input:Input
  out state_out:DoorState
  state -> unknown
  input -> unknown
  unknown -> state_out

""" + BASE + """
!actuator(state:DoorState):Receipt

>loop(value:DoorState):DoorState=loop(value)

>control(state:DoorState,input:Input):Receipt
  next := step(state,input)
  actuator(next)

>unknown(state:DoorState,input:Input):DoorState
  next := step(state,input)
  loop(next)
"""
        views = compile_source(source)
        transition = opening_transition(views)
        bindings = {
            item["system"]: item
            for item in transition["execution_action_bindings"]
        }
        self.assertEqual(bindings["DoorUnknown"]["status"], "unresolved")
        self.assertTrue(transition["action_scope"]["context_required"])
        self.assertIsNone(transition["display_action"])
        machine = views["state"]["machines"][0]
        self.assertTrue(
            any(item.get("code") == "STIR_SYSTEM_ACTION_UNRESOLVED" for item in machine["diagnostics"])
        )

    def test_guarded_system_entry_preserves_each_runtime_action_case(self) -> None:
        source = """system DoorControl
  entry control
  in state:DoorState
  in input:Input
  out receipt:Receipt
  state -> control
  input -> control
  control -> receipt
  control -> actuator
  control -> audit

""" + BASE.replace("*Input(open_request:B)", "*Input(open_request,authorized:B)") + """
!actuator(state:DoorState):Receipt
!audit(state:DoorState):Receipt

>control(state:DoorState,input:Input):Receipt
  input.authorized >> actuator(step(state,input))
  _ >> audit(step(state,input))
"""
        transition = opening_transition(compile_source(source))
        binding = transition["execution_action_bindings"][0]
        self.assertEqual(binding["status"], "conditional")
        cases = binding["action_cases"]
        self.assertEqual(len(cases), 2)
        by_action = {display(item["action"]): item for item in cases}
        self.assertIn("actuator(DoorState(Open))", by_action)
        self.assertIn("audit(DoorState(Open))", by_action)
        self.assertEqual(by_action["actuator(DoorState(Open))"]["condition"], "input.authorized")
        self.assertIn("!(input.authorized)", by_action["audit(DoorState(Open))"]["condition"])
        self.assertIn("actuator(DoorState(Open))", display(binding["action"]))
        self.assertIn("audit(DoorState(Open))", display(binding["action"]))

    def test_short_circuit_does_not_invent_rhs_action(self) -> None:
        source = """system DoorControl
  entry control
  in state:DoorState
  in input:Input
  out receipt:Receipt
  state -> control
  input -> control
  control -> receipt
  control -> audit
  control -> actuator

""" + BASE.replace("*Input(open_request:B)", "*Input(open_request,audit_enabled:B)") + """
!audit():B
!actuator(state:DoorState):Receipt

>control(state:DoorState,input:Input):Receipt
  next := step(state,input)
  checked := input.audit_enabled&audit()
  actuator(next)
"""
        transition = opening_transition(compile_source(source))
        binding = transition["execution_action_bindings"][0]
        self.assertEqual(binding["status"], "conditional")
        sequences = {
            tuple(item["expression"] for item in case["action_invocations"]): case["condition"]
            for case in binding["action_cases"]
        }
        self.assertIn(("actuator(DoorState(Open))",), sequences)
        self.assertIn(("audit()", "actuator(DoorState(Open))"), sequences)
        self.assertIn("!(input.audit_enabled)", sequences[("actuator(DoorState(Open))",)])
        self.assertEqual(
            sequences[("audit()", "actuator(DoorState(Open))")],
            "input.audit_enabled",
        )

    def test_try_expression_splits_success_continuation_and_failure_return(self) -> None:
        source = """system DoorControl
  entry control
  in state:DoorState
  in input:Input
  out receipt:R<Receipt,AuditError>
  state -> control
  input -> control
  control -> receipt
  control -> audit
  control -> actuator

""" + BASE + """
+AuditError=Rejected
!audit(state:DoorState):R<B,AuditError>
!actuator(state:DoorState):R<Receipt,AuditError>

>control(state:DoorState,input:Input):R<Receipt,AuditError>
  next := step(state,input)
  checked := audit(next)?
  actuator(next)
"""
        transition = opening_transition(compile_source(source))
        binding = transition["execution_action_bindings"][0]
        self.assertEqual(binding["status"], "conditional")
        success = next(
            item for item in binding["action_cases"] if item["reaches_continuation"]
        )
        failure = next(
            item for item in binding["action_cases"] if not item["reaches_continuation"]
        )
        self.assertEqual(
            [item["expression"] for item in success["action_invocations"]],
            ["audit(DoorState(Open))", "actuator(DoorState(Open))"],
        )
        self.assertEqual(
            [item["expression"] for item in failure["action_invocations"]],
            ["audit(DoorState(Open))"],
        )
        self.assertEqual(failure["outcome"], "failure-return")
        self.assertIn("success(audit(DoorState(Open)))", success["condition"])
        self.assertIn("failure(audit(DoorState(Open)))", failure["condition"])


if __name__ == "__main__":
    unittest.main()

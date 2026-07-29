from __future__ import annotations

import itertools
import unittest
from pathlib import Path

from glyph.compilation import CompilationPipeline
from glyph.compiler import BinaryExpr, BoolExpr, Expr, FieldExpr, NameExpr, UnaryExpr, parse_expr
from glyph.io_state_views import build_io_state_views


ROOT = Path(__file__).resolve().parents[1]


def compile_source(source: str, name: str = "enabling-cases-inline.glyph") -> dict[str, object]:
    output = CompilationPipeline().compile_text(source, source_name=name)
    return build_io_state_views(output.model, output.diagrams.ir)


def compile_example(relative: str) -> dict[str, object]:
    path = ROOT / relative
    return compile_source(path.read_text(encoding="utf-8"), str(path))


def action_display(transition: dict[str, object]) -> str:
    action = transition.get("action")
    if not isinstance(action, dict):
        return ""
    return str(action.get("display") or action.get("expression") or "")


def transition_for_action(machine: dict[str, object], action: str) -> dict[str, object]:
    return next(
        item
        for item in machine["transitions"]
        if action_display(item) == action
    )


def eval_bool(expression: Expr, assignment: dict[str, bool]) -> bool:
    if isinstance(expression, BoolExpr):
        return expression.value
    if isinstance(expression, NameExpr):
        return assignment[expression.name]
    if isinstance(expression, FieldExpr):
        if not isinstance(expression.base, NameExpr):
            raise AssertionError(f"unsupported field base: {expression}")
        return assignment[f"{expression.base.name}.{expression.field}"]
    if isinstance(expression, UnaryExpr) and expression.op == "!":
        return not eval_bool(expression.expr, assignment)
    if isinstance(expression, BinaryExpr):
        if expression.op == "&":
            return eval_bool(expression.left, assignment) and eval_bool(expression.right, assignment)
        if expression.op == "|":
            return eval_bool(expression.left, assignment) or eval_bool(expression.right, assignment)
        if expression.op == "==":
            return eval_bool(expression.left, assignment) == eval_bool(expression.right, assignment)
        if expression.op == "!=":
            return eval_bool(expression.left, assignment) != eval_bool(expression.right, assignment)
    raise AssertionError(f"unsupported Boolean expression: {expression}")


def assert_case_meaning_preserved(test: unittest.TestCase, case: dict[str, object], atoms: list[str]) -> None:
    exact = parse_expr(case["exact_enabling_condition"]["expression"])
    input_pattern = case.get("input_pattern")
    guard = case.get("guard")
    input_expr = (
        BoolExpr(True)
        if not isinstance(input_pattern, dict)
        else parse_expr(str(input_pattern["expression"]))
    )
    if case.get("fallback"):
        guard_expr = exact
    else:
        guard_expr = (
            BoolExpr(True)
            if not isinstance(guard, dict) or not guard.get("expression")
            else parse_expr(str(guard["expression"]))
        )
    combined = BinaryExpr("&", input_expr, guard_expr)
    for values in itertools.product((False, True), repeat=len(atoms)):
        assignment = dict(zip(atoms, values))
        test.assertEqual(
            eval_bool(exact, assignment),
            eval_bool(combined, assignment),
            f"meaning changed for {case['id']} at {assignment}",
        )


_DERIVED_GUARD_SOURCE = """\
machine Door(state:DoorState,input:Input)
  select=state.mode
  action=state.command
  init=DoorState(Locked,KeepLocked)
  next=step(state,input)
  success=Unlocked
  failure=Alarmed

*Input(request_open,authenticated:B)
+Command=KeepLocked|Unlock|RaiseAlarm
+Mode=Locked|Unlocked|Alarmed
*DoorState(mode:Mode,command:Command)

>authenticate(input:Input):B=input.authenticated

>decide(input:Input):Command
  input.request_open&authenticate(input) >> Unlock
  _ >> KeepLocked

>step(state:DoorState,input:Input):DoorState
  command := decide(input)
  next :=
    command==Unlock >> DoorState(Unlocked,Unlock)
    command==KeepLocked >> DoorState(Locked,KeepLocked)
    _ >> DoorState(Alarmed,RaiseAlarm)
  next
"""


_OR_CASE_SOURCE = """\
machine Choice(state:ChoiceState,input:Input)
  select=state.mode
  action=state.command
  init=ChoiceState(Idle,Stay)
  next=step(state,input)
  success=Active
  failure=Faulted

*Input(a,b:B)
+Command=Stay|Begin
+Mode=Idle|Active|Faulted
*ChoiceState(mode:Mode,command:Command)

>decide(input:Input):Command
  input.a|input.b >> Begin
  _ >> Stay

>step(state:ChoiceState,input:Input):ChoiceState
  command := decide(input)
  next :=
    command==Begin >> ChoiceState(Active,Begin)
    command==Stay >> ChoiceState(Idle,Stay)
    _ >> ChoiceState(Faulted,Stay)
  next
"""


_BASE_PRIORITY_SOURCE = """\
machine Motor(state:MotorState,input:Input)
  select=state.mode
  action=state.command
  init=MotorState(Stopped,DisableMotor)
  next=step(state,input)
  success=Stopped
  failure=Faulted

*Input(emergency,fault:B)
+Command=DisableMotor|EmergencyBrake|LatchFault
+Mode=Stopped|Faulted
*MotorState(mode:Mode,command:Command)

>decide(input:Input):Command
  input.emergency >> EmergencyBrake
  _ >> DisableMotor

>step(state:MotorState,input:Input):MotorState
  command := decide(input)
  next :=
    command==EmergencyBrake >> MotorState(Stopped,EmergencyBrake)
    command==DisableMotor >> MotorState(Stopped,DisableMotor)
    _ >> MotorState(Faulted,LatchFault)
  next
"""


class TransitionEnablingCaseTests(unittest.TestCase):
    def test_motor_priority_conditions_are_guards_not_input(self) -> None:
        views = compile_example("examples/acceptance/motor_safety.glyph")
        self.assertEqual(views["transition_enabling_case_version"], 1)
        machine = views["state"]["machines"][0]

        fault = transition_for_action(machine, "LatchFault")["enabling_cases"][0]
        self.assertEqual(fault["input_pattern"]["expression"], "input.fault")
        self.assertIsNone(fault["guard"])
        self.assertEqual(fault["exact_enabling_condition"]["expression"], "input.fault")

        emergency = transition_for_action(machine, "EmergencyBrake")["enabling_cases"][0]
        self.assertEqual(emergency["input_pattern"]["expression"], "input.emergency")
        self.assertEqual(emergency["guard"]["display"], "!input.fault")
        self.assertEqual(
            emergency["guard_terms"][0]["origin"],
            "priority-exclusion",
        )
        self.assertNotIn("input.fault", emergency["input_pattern"]["expression"])
        assert_case_meaning_preserved(
            self,
            emergency,
            ["input.emergency", "input.fault"],
        )

        disabled = transition_for_action(machine, "DisableMotor")["enabling_cases"][0]
        self.assertEqual(disabled["input_pattern"]["expression"], "!input.enabled")
        self.assertEqual(
            disabled["guard"]["display"],
            "!(input.fault|input.emergency)",
        )
        self.assertNotIn("input.fault", disabled["input_pattern"]["expression"])
        self.assertNotIn("input.emergency", disabled["input_pattern"]["expression"])
        assert_case_meaning_preserved(
            self,
            disabled,
            ["input.enabled", "input.fault", "input.emergency"],
        )

    def test_fallback_has_no_input_pattern_and_renders_as_guard(self) -> None:
        views = compile_example("examples/acceptance/motor_safety.glyph")
        machine = views["state"]["machines"][0]
        running = transition_for_action(
            machine,
            "SetMotorPower(normalize(input.raw))",
        )["enabling_cases"][0]
        self.assertIsNone(running["input_pattern"])
        self.assertTrue(running["fallback"])
        self.assertEqual(running["guard"]["display"], "otherwise")
        self.assertEqual(running["guard_terms"][0]["origin"], "fallback")

    def test_derived_predicate_is_guard_when_direct_input_exists(self) -> None:
        views = compile_source(_DERIVED_GUARD_SOURCE)
        machine = views["state"]["machines"][0]
        unlock = transition_for_action(machine, "Unlock")["enabling_cases"][0]
        self.assertEqual(unlock["input_pattern"]["expression"], "input.request_open")
        self.assertEqual(unlock["guard"]["display"], "authenticate(input)")
        self.assertEqual(
            unlock["guard_terms"][0]["origin"],
            "authored-derived-predicate",
        )

    def test_or_input_produces_distinct_enabling_cases(self) -> None:
        views = compile_source(_OR_CASE_SOURCE)
        machine = views["state"]["machines"][0]
        begin = transition_for_action(machine, "Begin")
        cases = begin["enabling_cases"]
        self.assertEqual(len(cases), 2)
        self.assertEqual(
            {item["input_pattern"]["expression"] for item in cases},
            {"input.a", "input.b"},
        )
        self.assertTrue(begin["legacy_projection_lossy"])

    def test_adding_prior_clause_changes_guard_only(self) -> None:
        baseline = compile_source(_BASE_PRIORITY_SOURCE)
        changed = compile_source(
            _BASE_PRIORITY_SOURCE.replace(
                "  input.emergency >> EmergencyBrake",
                "  input.fault >> LatchFault\n  input.emergency >> EmergencyBrake",
            )
        )
        baseline_machine = baseline["state"]["machines"][0]
        changed_machine = changed["state"]["machines"][0]
        baseline_transition = transition_for_action(baseline_machine, "EmergencyBrake")
        changed_transition = transition_for_action(changed_machine, "EmergencyBrake")
        baseline_case = baseline_transition["enabling_cases"][0]
        changed_case = changed_transition["enabling_cases"][0]

        self.assertEqual(
            baseline_case["input_pattern"]["expression"],
            "input.emergency",
        )
        self.assertEqual(
            changed_case["input_pattern"]["expression"],
            "input.emergency",
        )
        self.assertIsNone(baseline_case["guard"])
        self.assertEqual(changed_case["guard"]["display"], "!input.fault")
        self.assertEqual(action_display(baseline_transition), "EmergencyBrake")
        self.assertEqual(action_display(changed_transition), "EmergencyBrake")
        self.assertEqual(baseline_transition["target_state"], "Stopped")
        self.assertEqual(changed_transition["target_state"], "Stopped")

    def test_synthesized_failure_does_not_fabricate_case(self) -> None:
        views = compile_example("examples/acceptance/motor_safety.glyph")
        machine = views["state"]["machines"][0]
        for transition in machine["transitions"]:
            if transition.get("synthesized_failure"):
                self.assertEqual(transition.get("enabling_cases"), [])


if __name__ == "__main__":
    unittest.main()

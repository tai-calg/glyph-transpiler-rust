from __future__ import annotations

import unittest
from pathlib import Path

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views


ROOT = Path(__file__).resolve().parents[1]


def compile_source(source: str, name: str = "enabling-cases-inline.glyph") -> dict[str, object]:
    output = CompilationPipeline().compile_text(source, source_name=name)
    return build_io_state_views(output.model, output.diagrams.ir)


def compile_example(relative: str) -> dict[str, object]:
    path = ROOT / relative
    return compile_source(path.read_text(encoding="utf-8"), str(path))


def action_variant(transition: dict[str, object]) -> str:
    action = transition.get("action")
    return str(action.get("variant") or "") if isinstance(action, dict) else ""


def case_for(machine: dict[str, object], action: str) -> dict[str, object]:
    transition = next(
        item for item in machine["transitions"] if action_variant(item) == action
    )
    cases = transition.get("enabling_cases", [])
    if len(cases) != 1:
        raise AssertionError(f"expected one case for {action}, got {cases}")
    return cases[0]


class TransitionEnablingCasesTests(unittest.TestCase):
    def test_motor_ordered_clauses_keep_authored_input_and_generated_guard_separate(self) -> None:
        views = compile_example("examples/acceptance/motor_safety.glyph")
        machine = views["state"]["machines"][0]

        self.assertEqual(views["state_transition_ir"]["version"], 5)
        self.assertEqual(views["transition_enabling_cases_version"], 1)
        self.assertEqual(views["transition_semantics_version"], 2)

        fault = case_for(machine, "LatchFault")
        self.assertEqual(fault["input_pattern"]["expression"], "input.fault")
        self.assertIsNone(fault["guard"])
        self.assertEqual(fault["enabling_condition"]["expression"], "input.fault")

        emergency = case_for(machine, "EmergencyBrake")
        self.assertEqual(
            emergency["input_pattern"]["expression"],
            "input.emergency",
        )
        self.assertEqual(emergency["guard"]["display"], "!input.fault")
        self.assertEqual(
            emergency["guard"]["terms"][0]["origin"],
            "priority-exclusion",
        )
        self.assertEqual(
            emergency["enabling_condition"]["expression"],
            "input.emergency&!input.fault",
        )
        self.assertNotIn("!input.fault", emergency["input_pattern"]["expression"])

        disabled = case_for(machine, "DisableMotor")
        self.assertEqual(disabled["input_pattern"]["expression"], "!input.enabled")
        self.assertEqual(
            disabled["guard"]["display"],
            "!(input.fault|input.emergency)",
        )
        self.assertEqual(
            disabled["guard"]["terms"][0]["origin"],
            "priority-exclusion",
        )

        running = case_for(machine, "SetMotorPower")
        self.assertIsNone(running["input_pattern"])
        self.assertTrue(running["fallback"])
        self.assertEqual(running["guard"]["display"], "otherwise")
        self.assertEqual(running["guard"]["terms"][0]["origin"], "fallback")
        self.assertNotEqual(
            running["enabling_condition"]["expression"],
            "otherwise",
        )

    def test_input_derived_function_predicate_is_guard_not_input_pattern(self) -> None:
        source = """\
machine Door(state:DoorState,input:Input)
  select=state.mode
  action=state.action
  init=DoorState(Locked,KeepLocked)
  next=step(state,input)
  success=Unlocked
  failure=Alarmed

*Input(request_open,token:B)
+DoorAction=KeepLocked|Unlock|RaiseAlarm
+DoorMode=Locked|Unlocked|Alarmed
*DoorState(mode:DoorMode,action:DoorAction)

>authenticate(input:Input):B=input.token

>decide(input:Input):DoorAction
  input.request_open&authenticate(input) >> Unlock
  _ >> KeepLocked

>step(state:DoorState,input:Input):DoorState
  action := decide(input)
  next :=
    action==Unlock >> DoorState(Unlocked,Unlock)
    action==KeepLocked >> DoorState(Locked,KeepLocked)
    _ >> DoorState(Alarmed,RaiseAlarm)
  next
"""
        machine = compile_source(source)["state"]["machines"][0]
        unlocked = case_for(machine, "Unlock")
        self.assertEqual(
            unlocked["input_pattern"]["expression"],
            "input.request_open",
        )
        self.assertEqual(
            unlocked["guard"]["display"],
            "authenticate(input)",
        )
        self.assertEqual(
            unlocked["guard"]["terms"][0]["origin"],
            "authored-derived-predicate",
        )

    def test_priority_change_changes_guard_only(self) -> None:
        baseline = """\
machine M(state:S,input:I)
  select=state.mode
  action=state.action
  init=S(Idle,Wait)
  next=step(state,input)
  success=Active
  failure=Faulted
*I(start,fault:B)
+A=Wait|Begin|Fail
+Mode=Idle|Active|Faulted
*S(mode:Mode,action:A)
>decide(input:I):A
  input.start >> Begin
  _ >> Wait
>step(state:S,input:I):S
  action := decide(input)
  next :=
    action==Begin >> S(Active,Begin)
    action==Wait >> S(Idle,Wait)
    _ >> S(Faulted,Fail)
  next
"""
        changed = baseline.replace(
            "  input.start >> Begin",
            "  input.fault >> Fail\n  input.start >> Begin",
        ).replace(
            "    action==Begin >> S(Active,Begin)",
            "    action==Fail >> S(Faulted,Fail)\n    action==Begin >> S(Active,Begin)",
        )
        before = case_for(compile_source(baseline)["state"]["machines"][0], "Begin")
        after = case_for(compile_source(changed)["state"]["machines"][0], "Begin")
        self.assertEqual(before["input_pattern"], after["input_pattern"])
        self.assertIsNone(before["guard"])
        self.assertEqual(after["guard"]["display"], "!input.fault")

    def test_same_result_clauses_remain_separate_cases(self) -> None:
        source = """\
machine M(state:S,input:I)
  select=state.mode
  action=state.action
  init=S(Idle,Wait)
  next=step(state,input)
  success=Idle
  failure=Faulted
*I(a,b:B)
+A=Wait|Stop
+Mode=Idle|Faulted
*S(mode:Mode,action:A)
>decide(input:I):A
  input.a >> Stop
  input.b >> Stop
  _ >> Wait
>step(state:S,input:I):S
  action := decide(input)
  next :=
    action==Stop >> S(Idle,Stop)
    action==Wait >> S(Idle,Wait)
    _ >> S(Faulted,Wait)
  next
"""
        machine = compile_source(source)["state"]["machines"][0]
        transition = next(
            item for item in machine["transitions"] if action_variant(item) == "Stop"
        )
        cases = transition["enabling_cases"]
        self.assertEqual(len(cases), 2)
        self.assertEqual(
            [item["input_pattern"]["expression"] for item in cases],
            ["input.a", "input.b"],
        )
        self.assertTrue(transition["legacy_projection_lossy"])


if __name__ == "__main__":
    unittest.main()

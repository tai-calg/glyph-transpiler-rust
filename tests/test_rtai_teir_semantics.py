from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.compiler import BoolExpr, CallExpr, FieldExpr, NameExpr
from glyph.transition_analysis.concrete import (
    ConcreteInterpreter,
    ConstructorValue,
    ResultValue,
    VariantValue,
)
from glyph.transition_analysis.lowering import lower_compilation_model
from glyph.transition_analysis.machine_relation import build_machine_relation
from glyph.transition_analysis.oracle import compare_bounded_ast_and_teir
from glyph.transition_analysis.preimage import (
    PreimageStatus,
    compute_transition_call_preimage,
)
from glyph.transition_analysis.teir import Branch, TransitionCall


DOOR_SOURCE = """system DoorControl
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
  actuator(next)
"""


CONDITIONAL_BLOCK_SOURCE = """*Input(open_request:B)
+DoorMode=Closed|Open

>choose(input:Input):DoorMode
  selected :=
    input.open_request => Open
    _ => Closed
  selected
"""


FAILURE_SOURCE = """system PumpControl
  entry control

  in state:PumpState
  in event:PumpEvent
  out state_out:PumpState

  state -> control
  event -> control
  control -> state_out
  control -> actuator
  control -> write_pump

machine Pump(state:PumpState,event:PumpEvent)
  select=state.mode
  init=PumpState(Off)
  next=pump_step(state,event)
  success=On
  failure=Fault

+PumpEvent=Start|Stop
+PumpMode=Off|On|Fault
+WriteError=IoError
+Receipt=Written(B)
*PumpState(mode:PumpMode)

!write_pump(enabled:B):Receipt|WriteError
!actuator(state:PumpState):PumpState

>pump_step(state:PumpState,event:PumpEvent):PumpState|WriteError
  event==Start >> Ok(PumpState(On))
  event==Stop >> Ok(PumpState(Off))
  _ >> Ok(state)

>control(state:PumpState,event:PumpEvent):PumpState|WriteError
  next := pump_step(state,event)?
  receipt := write_pump(next.mode==On)?
  Ok(actuator(next))
"""


def compile_model(source: str, name: str):
    return CompilationPipeline().compile_text(source, source_name=name).model


class TeirLoweringTests(unittest.TestCase):
    def test_block_and_guard_syntax_lower_to_cfg(self) -> None:
        model = compile_model(CONDITIONAL_BLOCK_SOURCE, "conditional-block.glyph")
        functions = lower_compilation_model(model)
        choose = functions["choose"]
        self.assertGreaterEqual(len(choose.blocks), 4)
        self.assertTrue(
            any(isinstance(block.terminator, Branch) for block in choose.blocks)
        )

    def test_direct_machine_call_is_explicit_transition_instruction(self) -> None:
        model = compile_model(DOOR_SOURCE, "door-teir.glyph")
        control = lower_compilation_model(model)["control"]
        instructions = [
            instruction
            for block in control.blocks
            for instruction in block.instructions
        ]
        calls = [item for item in instructions if isinstance(item, TransitionCall)]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].machine, "Door")
        self.assertEqual(calls[0].function, "step")


class MachineRelationTests(unittest.TestCase):
    def test_ordered_guards_are_normalized_once(self) -> None:
        model = compile_model(DOOR_SOURCE, "door-relation.glyph")
        relation = build_machine_relation(model, "Door")
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(len(relation.edges), 3)
        self.assertEqual([edge.ordinal for edge in relation.edges], [0, 1, 2])
        self.assertEqual(
            [edge.target_state for edge in relation.edges],
            ["Open", "Alarm", "__same__"],
        )
        self.assertTrue(relation.approximation.is_exact)
        self.assertIn("UnaryExpr", repr(relation.edges[1].effective_guard))
        self.assertIn("UnaryExpr", repr(relation.edges[2].effective_guard))


class RelationalPreimageTests(unittest.TestCase):
    def test_field_permutation_changes_the_substituted_preimage(self) -> None:
        model = compile_model(DOOR_SOURCE, "door-preimage-permutation.glyph")
        state = CallExpr(NameExpr("DoorState"), (NameExpr("Closed"),))
        normal_input = CallExpr(
            NameExpr("Input"),
            (
                FieldExpr(NameExpr("input"), "open_request"),
                FieldExpr(NameExpr("input"), "authorized"),
            ),
        )
        swapped_input = CallExpr(
            NameExpr("Input"),
            (
                FieldExpr(NameExpr("input"), "authorized"),
                FieldExpr(NameExpr("input"), "open_request"),
            ),
        )
        normal = compute_transition_call_preimage(model, "Door", (state, normal_input))
        swapped = compute_transition_call_preimage(model, "Door", (state, swapped_input))
        self.assertIsNotNone(normal)
        self.assertIsNotNone(swapped)
        assert normal is not None and swapped is not None
        self.assertNotEqual(
            repr(normal.edges[1].condition),
            repr(swapped.edges[1].condition),
        )
        self.assertIn("authorized", repr(swapped.edges[1].condition))

    def test_concrete_constructor_arguments_prove_selected_edges(self) -> None:
        model = compile_model(DOOR_SOURCE, "door-preimage-concrete.glyph")
        state = CallExpr(NameExpr("DoorState"), (NameExpr("Closed"),))
        event = CallExpr(NameExpr("Input"), (BoolExpr(True), BoolExpr(False)))
        preimage = compute_transition_call_preimage(model, "Door", (state, event))
        self.assertIsNotNone(preimage)
        assert preimage is not None
        self.assertEqual(preimage.edges[0].status, PreimageStatus.PROVEN_FALSE)
        self.assertEqual(preimage.edges[1].status, PreimageStatus.PROVEN_TRUE)
        self.assertEqual(preimage.edges[2].status, PreimageStatus.PROVEN_FALSE)


class ConcreteOracleTests(unittest.TestCase):
    def test_finite_block_domain_matches_source_and_teir(self) -> None:
        model = compile_model(CONDITIONAL_BLOCK_SOURCE, "conditional-oracle.glyph")
        report = compare_bounded_ast_and_teir(model, "choose")
        self.assertEqual(len(report.cases), 2)
        self.assertTrue(report.exact, report.mismatches)

    def test_door_system_matches_for_all_finite_inputs(self) -> None:
        model = compile_model(DOOR_SOURCE, "door-oracle.glyph")
        report = compare_bounded_ast_and_teir(
            model,
            "control",
            effect_handlers={"actuator": lambda arguments: arguments[0]},
        )
        self.assertEqual(len(report.cases), 12)
        self.assertTrue(report.exact, report.mismatches[:1])
        self.assertTrue(
            all(len(case.teir.transition_trace) == 1 for case in report.cases)
        )
        self.assertTrue(all(len(case.teir.effect_trace) == 1 for case in report.cases))

    def test_concrete_edge_and_effect_are_correlated(self) -> None:
        model = compile_model(DOOR_SOURCE, "door-edge.glyph")
        interpreter = ConcreteInterpreter(
            model,
            effect_handlers={"actuator": lambda arguments: arguments[0]},
        )
        state = ConstructorValue("DoorState", (("mode", VariantValue("Closed")),))
        event = ConstructorValue(
            "Input",
            (("open_request", True), ("authorized", False)),
        )
        result = interpreter.run("control", (state, event))
        self.assertEqual(result.completion, "returned")
        self.assertEqual(result.transition_trace[0].result, result.effect_trace[0].arguments[0])
        self.assertEqual(
            result.return_value,
            ConstructorValue("DoorState", (("mode", VariantValue("Alarm")),)),
        )

    def test_failure_stops_post_failure_effects(self) -> None:
        model = compile_model(FAILURE_SOURCE, "failure-oracle.glyph")
        handlers = {
            "write_pump": lambda arguments: (
                ResultValue(False, VariantValue("IoError"))
                if arguments[0]
                else ResultValue(True, VariantValue("Written", (False,)))
            ),
            "actuator": lambda arguments: arguments[0],
        }
        report = compare_bounded_ast_and_teir(
            model,
            "control",
            effect_handlers=handlers,
        )
        self.assertTrue(report.exact, report.mismatches[:1])
        failed = [
            case.teir
            for case in report.cases
            if case.teir.completion == "propagated-failure"
        ]
        self.assertTrue(failed)
        for result in failed:
            self.assertEqual(
                [event.operation for event in result.effect_trace],
                ["write_pump"],
            )
            self.assertNotIn("actuator", [event.operation for event in result.effect_trace])


if __name__ == "__main__":
    unittest.main()

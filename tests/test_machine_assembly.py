from __future__ import annotations

import unittest

from glyph import parse_compilation_model
from glyph.assembly import extract_assemblies
from glyph.assembly_frontend import AssemblyCompilationModel
from glyph.assembly_runtime import EffectInvocation, ImmediateAssemblyRuntime
from glyph.compiler import GlyphError


VALID = """\
+DoorInput=BadgeAccepted|ForcedOpen
+DoorMode=DoorLocked|DoorUnlocked|DoorFaulted
*DoorState(mode:DoorMode)

+SafetyInput=EmergencyDetected
+SafetyMode=SafetyNormal|SafetyEmergency|SafetyFaulted
*SafetyState(mode:SafetyMode)

+MotorInput=StopRequested
+MotorMode=MotorRunning|MotorStopped|MotorFaulted
*MotorState(mode:MotorMode)

+MotorCommand=DisableMotor
*Receipt(command:MotorCommand)

!notify_safety(event:SafetyInput):()
!request_motor(event:MotorInput):()
!write_motor(command:MotorCommand):Receipt=Receipt(command)

>door_fault(state:DoorState):DoorState
  notice := notify_safety(EmergencyDetected)
  DoorState(DoorFaulted)

>door_next(state:DoorState,input:DoorInput):DoorState
  state.mode==DoorLocked&input==ForcedOpen>>door_fault(state)
  state.mode==DoorLocked&input==BadgeAccepted>>DoorState(DoorUnlocked)
  _>>state

>safety_emergency(state:SafetyState):SafetyState
  request := request_motor(StopRequested)
  SafetyState(SafetyEmergency)

>safety_next(state:SafetyState,input:SafetyInput):SafetyState
  input==EmergencyDetected>>safety_emergency(state)
  _>>state

>motor_stop(state:MotorState):MotorState
  receipt := write_motor(DisableMotor)
  MotorState(MotorStopped)

>motor_next(state:MotorState,input:MotorInput):MotorState
  input==StopRequested>>motor_stop(state)
  _>>state

machine Door(state:DoorState,input:DoorInput)
  select=state.mode
  init=DoorState(DoorLocked)
  next=door_next(state,input)
  success=DoorUnlocked
  failure=DoorFaulted

machine Safety(state:SafetyState,input:SafetyInput)
  select=state.mode
  init=SafetyState(SafetyNormal)
  next=safety_next(state,input)
  success=SafetyEmergency
  failure=SafetyFaulted

machine Motor(state:MotorState,input:MotorInput)
  select=state.mode
  init=MotorState(MotorRunning)
  next=motor_next(state,input)
  success=MotorStopped
  failure=MotorFaulted

assembly DoorControl
  door=Door
  safety=Safety
  motor=Motor

  door.notify_safety -> safety.input
  safety.request_motor -> motor.input
"""


INITIAL = {
    "door": "DoorLocked",
    "safety": "SafetyNormal",
    "motor": "MotorRunning",
}


class MachineAssemblyTests(unittest.TestCase):
    def test_public_compilation_returns_immutable_assembly_model(self) -> None:
        model = parse_compilation_model(VALID)

        self.assertIsInstance(model, AssemblyCompilationModel)
        self.assertEqual(model.assembly_source, VALID)
        self.assertEqual([item.name for item in model.assemblies], ["DoorControl"])
        self.assertEqual(len(model.assembly_ir), 1)
        ir = model.assembly_ir[0]
        self.assertEqual(ir.delivery, "immediate-call-point")
        self.assertEqual(ir.state_commit, "atomic-per-top-level-reaction")
        self.assertEqual(ir.reentrant_reaction, "forbidden")
        self.assertEqual(
            [
                (
                    route["source_instance"],
                    route["effect"],
                    route["payload_parameter"],
                    route["target_instance"],
                )
                for route in ir.routes
            ],
            [
                ("door", "notify_safety", "event", "safety"),
                ("safety", "request_motor", "event", "motor"),
            ],
        )

    def test_extraction_preserves_source_line_count(self) -> None:
        stripped, assemblies = extract_assemblies(VALID)
        self.assertEqual(len(stripped.splitlines()), len(VALID.splitlines()))
        self.assertEqual(len(assemblies), 1)
        self.assertNotIn("assembly DoorControl", stripped)

    def test_route_argument_type_must_match_target_input(self) -> None:
        source = VALID.replace(
            "!notify_safety(event:SafetyInput):()",
            "!notify_safety(event:MotorInput):()",
        )
        with self.assertRaisesRegex(GlyphError, "route型不一致"):
            parse_compilation_model(source)

    def test_internal_route_is_one_argument_and_unit_result(self) -> None:
        wrong_result = VALID.replace(
            "!notify_safety(event:SafetyInput):()",
            "!notify_safety(event:SafetyInput):SafetyInput",
        )
        with self.assertRaisesRegex(GlyphError, r"戻り値は\(\)が必要"):
            parse_compilation_model(wrong_result)

        wrong_arity = VALID.replace(
            "!notify_safety(event:SafetyInput):()",
            "!notify_safety(event:SafetyInput,context:B):()",
        )
        with self.assertRaisesRegex(GlyphError, "payload引数を1つ"):
            parse_compilation_model(wrong_arity)

    def test_source_effect_must_be_reachable_from_source_machine(self) -> None:
        source = VALID.replace(
            "door.notify_safety -> safety.input",
            "door.request_motor -> motor.input",
        ).replace("  safety.request_motor -> motor.input\n", "")
        with self.assertRaisesRegex(GlyphError, "遷移Actionから到達できない"):
            parse_compilation_model(source)

    def test_v1_rejects_fanout_from_one_effect(self) -> None:
        source = VALID.replace(
            "  door.notify_safety -> safety.input\n",
            "  door.notify_safety -> safety.input\n"
            "  door.notify_safety -> safety.input\n",
        )
        with self.assertRaisesRegex(GlyphError, "v1は単一接続のみ"):
            parse_compilation_model(source)

    def test_stateful_runtime_routes_arguments_and_returns_host_results(self) -> None:
        model = parse_compilation_model(VALID)
        runtime = ImmediateAssemblyRuntime(model.assembly_ir[0], INITIAL)

        def handler(instance: str, input_name: str, value: object, state: object):
            if instance == "door":
                routed_result = yield EffectInvocation(
                    "notify_safety", "EmergencyDetected"
                )
                self.assertIsNone(routed_result)
                return "DoorFaulted"
            if instance == "safety":
                yield EffectInvocation("request_motor", "StopRequested")
                return "SafetyEmergency"
            if instance == "motor":
                receipt = yield EffectInvocation("write_motor", "DisableMotor")
                self.assertEqual(receipt, "Receipt(DisableMotor)")
                return "MotorStopped"
            self.fail(instance)

        def host(instance: str, effect: str, arguments: tuple[object, ...]):
            self.assertEqual((instance, effect), ("motor", "write_motor"))
            return f"Receipt({arguments[0]})"

        result = runtime.react("door", "input", "ForcedOpen", handler, host)
        enters = [item for item in result.trace if item.phase == "enter"]
        self.assertEqual(
            [(item.instance, item.input, item.depth) for item in enters],
            [
                ("door", "input", 0),
                ("safety", "input", 1),
                ("motor", "input", 2),
            ],
        )
        self.assertEqual(
            [
                (item.instance, item.effect, item.arguments, item.result)
                for item in result.external_effects
            ],
            [
                (
                    "motor",
                    "write_motor",
                    ("DisableMotor",),
                    "Receipt(DisableMotor)",
                )
            ],
        )
        self.assertEqual(
            result.states,
            {
                "door": "DoorFaulted",
                "safety": "SafetyEmergency",
                "motor": "MotorStopped",
            },
        )

    def test_reentry_failure_rolls_back_all_machine_states(self) -> None:
        model = parse_compilation_model(VALID)
        ir = model.assembly_ir[0]
        cyclic_routes = (
            *ir.routes,
            {
                "source_instance": "motor",
                "source_machine": "Motor",
                "effect": "write_motor",
                "payload_parameter": "command",
                "payload_type": "DoorInput",
                "result_type": "()",
                "target_instance": "door",
                "target_machine": "Door",
                "input": "input",
                "delivery": "immediate",
                "order": 3,
                "line": 1,
            },
        )
        cyclic_ir = type(ir)(
            schema=ir.schema,
            version=ir.version,
            name=ir.name,
            delivery=ir.delivery,
            state_commit=ir.state_commit,
            reentrant_reaction=ir.reentrant_reaction,
            instances=ir.instances,
            routes=cyclic_routes,
            diagnostics=ir.diagnostics,
        )
        runtime = ImmediateAssemblyRuntime(cyclic_ir, INITIAL)

        def handler(instance: str, input_name: str, value: object, state: object):
            effects = {
                "door": EffectInvocation("notify_safety", "EmergencyDetected"),
                "safety": EffectInvocation("request_motor", "StopRequested"),
                "motor": EffectInvocation("write_motor", "ForcedOpen"),
            }
            yield effects[instance]
            return f"changed-{instance}"

        with self.assertRaisesRegex(GlyphError, "再入は禁止"):
            runtime.react("door", "input", "ForcedOpen", handler)
        self.assertEqual(runtime.states, INITIAL)

    def test_runtime_rejects_unknown_input_and_effect(self) -> None:
        model = parse_compilation_model(VALID)
        runtime = ImmediateAssemblyRuntime(model.assembly_ir[0], INITIAL)

        def no_effect(instance: str, input_name: str, value: object, state: object):
            if False:
                yield EffectInvocation("never")
            return state

        with self.assertRaisesRegex(GlyphError, "入力 'missing' がない"):
            runtime.react("door", "missing", "ForcedOpen", no_effect)

        def unknown_effect(instance: str, input_name: str, value: object, state: object):
            yield EffectInvocation("typo", value)
            return state

        with self.assertRaisesRegex(GlyphError, "遷移Actionとして宣言されていない"):
            runtime.react("door", "input", "ForcedOpen", unknown_effect)


if __name__ == "__main__":
    unittest.main()

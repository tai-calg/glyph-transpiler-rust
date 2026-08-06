from __future__ import annotations

import unittest

from glyph import parse_compilation_model
from glyph.assembly import extract_assemblies
from glyph.assembly_runtime import EffectEmission, ImmediateAssemblyRuntime
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

!notify_safety(event:SafetyInput):SafetyInput=event
!request_motor(event:MotorInput):MotorInput=event
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


class MachineAssemblyTests(unittest.TestCase):
    def test_public_compilation_extracts_and_validates_assembly(self) -> None:
        model = parse_compilation_model(VALID)

        self.assertEqual([item.name for item in model.assemblies], ["DoorControl"])
        self.assertEqual(len(model.assembly_ir), 1)
        ir = model.assembly_ir[0]
        self.assertEqual(ir.delivery, "immediate")
        self.assertEqual(ir.reentrant_reaction, "forbidden")
        self.assertEqual(
            [
                (
                    route["source_instance"],
                    route["effect"],
                    route["target_instance"],
                )
                for route in ir.routes
            ],
            [
                ("door", "notify_safety", "safety"),
                ("safety", "request_motor", "motor"),
            ],
        )

    def test_extraction_preserves_source_line_count(self) -> None:
        stripped, assemblies = extract_assemblies(VALID)
        self.assertEqual(len(stripped.splitlines()), len(VALID.splitlines()))
        self.assertEqual(len(assemblies), 1)
        self.assertNotIn("assembly DoorControl", stripped)

    def test_route_return_type_must_match_target_input(self) -> None:
        source = VALID.replace(
            "!notify_safety(event:SafetyInput):SafetyInput=event",
            "!notify_safety(event:SafetyInput):MotorInput=StopRequested",
        )
        with self.assertRaisesRegex(GlyphError, "route型不一致"):
            parse_compilation_model(source)

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

    def test_immediate_runtime_propagates_depth_first_and_leaves_host_effects(self) -> None:
        model = parse_compilation_model(VALID)
        runtime = ImmediateAssemblyRuntime(model.assembly_ir[0])

        def handler(instance: str, input_name: str, value: object):
            if instance == "door":
                return [EffectEmission("notify_safety", "EmergencyDetected")]
            if instance == "safety":
                return [EffectEmission("request_motor", "StopRequested")]
            if instance == "motor":
                return [EffectEmission("write_motor", "DisableMotor")]
            self.fail(instance)

        result = runtime.react("door", "input", "ForcedOpen", handler)
        self.assertEqual(
            [(item.instance, item.input, item.depth) for item in result.trace],
            [
                ("door", "input", 0),
                ("safety", "input", 1),
                ("motor", "input", 2),
            ],
        )
        self.assertEqual(
            [
                (item.instance, item.effect, item.value)
                for item in result.external_effects
            ],
            [("motor", "write_motor", "DisableMotor")],
        )

    def test_immediate_runtime_rejects_reentry(self) -> None:
        model = parse_compilation_model(VALID)
        ir = model.assembly_ir[0]
        cyclic_routes = (
            *ir.routes,
            {
                "source_instance": "motor",
                "source_machine": "Motor",
                "effect": "write_motor",
                "value_type": "DoorInput",
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
            reentrant_reaction=ir.reentrant_reaction,
            instances=ir.instances,
            routes=cyclic_routes,
            diagnostics=ir.diagnostics,
        )
        runtime = ImmediateAssemblyRuntime(cyclic_ir)

        def handler(instance: str, input_name: str, value: object):
            effects = {
                "door": EffectEmission("notify_safety", "EmergencyDetected"),
                "safety": EffectEmission("request_motor", "StopRequested"),
                "motor": EffectEmission("write_motor", "ForcedOpen"),
            }
            return [effects[instance]]

        with self.assertRaisesRegex(GlyphError, "再入は禁止"):
            runtime.react("door", "input", "ForcedOpen", handler)


if __name__ == "__main__":
    unittest.main()

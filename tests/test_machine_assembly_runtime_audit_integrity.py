from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from glyph import parse_compilation_model
from glyph.assembly import FrozenMapping
from glyph.assembly_runtime import (
    EffectInvocation,
    ImmediateAssemblyRuntime,
    ImmediateReactionFailureAudit,
)
from glyph.compiler import GlyphError


SOURCE = Path("examples/machine_assembly_immediate.glyph").read_text(encoding="utf-8")
INITIAL = {
    "door": {"mode": "DoorLocked"},
    "safety": {"mode": "SafetyNormal"},
    "motor": {"mode": "MotorRunning"},
}


class MachineAssemblyRuntimeAuditIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ir = parse_compilation_model(SOURCE).assembly_ir[0]

    def test_custom_state_cloner_cannot_bypass_deepcopy(self) -> None:
        with self.assertRaises(TypeError):
            ImmediateAssemblyRuntime(
                self.ir,
                INITIAL,
                state_cloner=lambda value: value,
            )

    def test_success_result_and_audit_values_are_recursively_immutable(self) -> None:
        runtime = ImmediateAssemblyRuntime(self.ir, INITIAL)

        def handler(instance, input_name, value, state):
            receipt = yield EffectInvocation("write_motor", "DisableMotor")
            self.assertEqual(receipt, {"command": "DisableMotor"})
            return {"mode": "MotorStopped"}

        def host(instance, effect, arguments):
            return {"command": arguments[0]}

        result = runtime.react("motor", "input", "StopRequested", handler, host)
        self.assertEqual(result.states["motor"], {"mode": "MotorStopped"})
        self.assertEqual(result.external_effects[0].status, "validated")

        with self.assertRaises(TypeError):
            result.states["motor"] = {"mode": "MotorRunning"}
        with self.assertRaises(TypeError):
            result.states["motor"]["mode"] = "MotorRunning"
        with self.assertRaises(TypeError):
            result.external_effects[0].result["command"] = "Other"
        with self.assertRaises(TypeError):
            result.trace[0].state["mode"] = "Other"

    def test_completed_host_effect_is_preserved_on_downstream_failure(self) -> None:
        runtime = ImmediateAssemblyRuntime(self.ir, INITIAL)

        def handler(instance, input_name, value, state):
            yield EffectInvocation("write_motor", "DisableMotor")
            return {"mode": "DoorLocked"}

        def host(instance, effect, arguments):
            return {"command": arguments[0]}

        with self.assertRaises(GlyphError) as caught:
            runtime.react("motor", "input", "StopRequested", handler, host)

        audit = caught.exception.assembly_audit
        self.assertIsInstance(audit, ImmediateReactionFailureAudit)
        self.assertEqual(len(audit.external_effects), 1)
        self.assertEqual(audit.external_effects[0].status, "validated")
        self.assertEqual(
            audit.external_effects[0].result,
            {"command": "DisableMotor"},
        )
        self.assertEqual(audit.committed_states, INITIAL)
        self.assertEqual(runtime.states, INITIAL)
        with self.assertRaises(TypeError):
            audit.external_effects[0].result["command"] = "Other"

    def test_invalid_host_result_is_recorded_before_validation_error(self) -> None:
        runtime = ImmediateAssemblyRuntime(self.ir, INITIAL)

        def handler(instance, input_name, value, state):
            yield EffectInvocation("write_motor", "DisableMotor")
            return state

        def host(instance, effect, arguments):
            return {"wrong": arguments[0]}

        with self.assertRaises(GlyphError) as caught:
            runtime.react("motor", "input", "StopRequested", handler, host)

        effect = caught.exception.assembly_audit.external_effects[0]
        self.assertEqual(effect.status, "invalid-result")
        self.assertIn("product型 'Receipt'", effect.error)
        self.assertEqual(effect.result, {"wrong": "DisableMotor"})

    def test_host_exception_keeps_original_type_and_failure_audit(self) -> None:
        runtime = ImmediateAssemblyRuntime(self.ir, INITIAL)

        def handler(instance, input_name, value, state):
            yield EffectInvocation("write_motor", "DisableMotor")
            return state

        def host(instance, effect, arguments):
            raise RuntimeError("bus failed")

        with self.assertRaisesRegex(RuntimeError, "bus failed") as caught:
            runtime.react("motor", "input", "StopRequested", handler, host)

        effect = caught.exception.assembly_audit.external_effects[0]
        self.assertEqual(effect.status, "raised")
        self.assertIn("RuntimeError: bus failed", effect.error)
        self.assertEqual(runtime.states, INITIAL)

    def test_runtime_rejects_duplicate_and_broken_ir_records(self) -> None:
        duplicate_instance_ir = replace(
            self.ir,
            instances=(self.ir.instances[0], *self.ir.instances),
        )
        with self.assertRaisesRegex(GlyphError, "重複instance名"):
            ImmediateAssemblyRuntime(duplicate_instance_ir, INITIAL)

        duplicate_type_ir = replace(
            self.ir,
            types=(self.ir.types[0], *self.ir.types),
        )
        with self.assertRaisesRegex(GlyphError, "重複type名"):
            ImmediateAssemblyRuntime(duplicate_type_ir, INITIAL)

        route = dict(self.ir.routes[0])
        route["target_instance"] = "missing"
        broken_route_ir = replace(
            self.ir,
            routes=(route, *self.ir.routes[1:]),
        )
        with self.assertRaisesRegex(GlyphError, "target instance 'missing'"):
            ImmediateAssemblyRuntime(broken_route_ir, INITIAL)

        mismatched = dict(self.ir.routes[0])
        mismatched["payload_type_ref"] = {
            "name": "MotorInput",
            "arguments": (),
        }
        mismatched_route_ir = replace(
            self.ir,
            routes=(mismatched, *self.ir.routes[1:]),
        )
        with self.assertRaisesRegex(GlyphError, "route payload型"):
            ImmediateAssemblyRuntime(mismatched_route_ir, INITIAL)

    def test_ir_freeze_rejects_unrepresentable_mutable_objects(self) -> None:
        with self.assertRaisesRegex(TypeError, "Assembly IRに保持できない"):
            FrozenMapping({"bad": object()})


if __name__ == "__main__":
    unittest.main()

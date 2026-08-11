from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
import unittest

from glyph import parse_compilation_model
from glyph.assembly import FrozenMapping
from glyph.assembly_runtime import (
    EffectInvocation,
    FrozenObjectSnapshot,
    ImmediateAssemblyRuntime,
)
from glyph.compiler import GlyphError


SOURCE = Path("examples/machine_assembly_immediate.glyph").read_text(encoding="utf-8")
INITIAL = {
    "door": {"mode": "DoorLocked"},
    "safety": {"mode": "SafetyNormal"},
    "motor": {"mode": "MotorRunning"},
}


class DeepcopyTrapDict(dict):
    def __deepcopy__(self, memo):
        raise AssertionError("Runtime must not invoke Python deepcopy protocol")


class BadStringError(RuntimeError):
    def __str__(self) -> str:
        raise RuntimeError("stringification failed")


class SnapshotHostileReceipt(dict):
    def items(self):
        raise RuntimeError("audit iteration disabled")

    def __repr__(self) -> str:
        raise RuntimeError("repr disabled")


class DuplicateItemsMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        if key == "x":
            return 1
        raise KeyError(key)

    def __iter__(self):
        return iter(("x",))

    def __len__(self) -> int:
        return 1

    def items(self):
        return (("x", 1), ("x", 2))


class MachineAssemblyRuntimeFinalHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ir = parse_compilation_model(SOURCE).assembly_ir[0]

    def test_structural_clone_ignores_hostile_deepcopy_protocol(self) -> None:
        initial = dict(INITIAL)
        motor = DeepcopyTrapDict({"mode": "MotorRunning"})
        initial["motor"] = motor
        runtime = ImmediateAssemblyRuntime(self.ir, initial)

        def handler(instance, input_name, value, state):
            if False:
                yield EffectInvocation("never")
            state["mode"] = "MotorStopped"
            raise RuntimeError("abort")

        with self.assertRaisesRegex(RuntimeError, "abort"):
            runtime.react("motor", "input", "StopRequested", handler)

        self.assertEqual(runtime.states["motor"], {"mode": "MotorRunning"})
        self.assertEqual(motor, {"mode": "MotorRunning"})

    def test_failure_trace_uses_stage_not_false_commit(self) -> None:
        runtime = ImmediateAssemblyRuntime(self.ir, INITIAL)

        def handler(instance, input_name, value, state):
            if instance == "door":
                yield EffectInvocation("notify_safety", "EmergencyDetected")
                return {"mode": "MotorStopped"}
            if instance == "safety":
                yield EffectInvocation("request_motor", "StopRequested")
                return {"mode": "SafetyEmergency"}
            if instance == "motor":
                yield EffectInvocation("write_motor", "DisableMotor")
                return {"mode": "MotorStopped"}
            raise AssertionError(instance)

        def host(instance, effect, arguments):
            return {"command": arguments[0]}

        with self.assertRaises(GlyphError) as caught:
            runtime.react("door", "input", "ForcedOpen", handler, host)

        phases = [entry.phase for entry in caught.exception.assembly_audit.trace]
        self.assertIn("stage", phases)
        self.assertNotIn("commit", phases)
        self.assertEqual(caught.exception.assembly_audit.committed_states, INITIAL)
        self.assertEqual(runtime.states, INITIAL)

    def test_audit_stringification_failure_cannot_mask_host_error(self) -> None:
        runtime = ImmediateAssemblyRuntime(self.ir, INITIAL)

        def handler(instance, input_name, value, state):
            yield EffectInvocation("write_motor", "DisableMotor")
            return state

        def host(instance, effect, arguments):
            raise BadStringError()

        with self.assertRaises(BadStringError) as caught:
            runtime.react("motor", "input", "StopRequested", handler, host)

        effect = caught.exception.assembly_audit.external_effects[0]
        self.assertEqual(effect.status, "raised")
        self.assertIn("<message unavailable>", effect.error)

    def test_audit_snapshot_failure_is_non_fatal(self) -> None:
        runtime = ImmediateAssemblyRuntime(self.ir, INITIAL)

        def handler(instance, input_name, value, state):
            receipt = yield EffectInvocation("write_motor", "DisableMotor")
            self.assertEqual(receipt, {"command": "DisableMotor"})
            return {"mode": "MotorStopped"}

        def host(instance, effect, arguments):
            return SnapshotHostileReceipt({"command": arguments[0]})

        result = runtime.react("motor", "input", "StopRequested", handler, host)
        effect = result.external_effects[0]
        self.assertEqual(effect.status, "validated")
        self.assertIsInstance(effect.result, FrozenObjectSnapshot)
        self.assertIn("$snapshot_error", effect.result.attributes)

    def test_frozen_mapping_rejects_non_string_and_duplicate_keys(self) -> None:
        with self.assertRaisesRegex(TypeError, "keyはstr"):
            FrozenMapping({1: "integer", "1": "string"})
        with self.assertRaisesRegex(TypeError, "重複"):
            FrozenMapping(DuplicateItemsMapping())

    def test_runtime_rejects_reserved_builtin_type_definition(self) -> None:
        bad_ir = replace(
            self.ir,
            types=(
                {
                    "name": "Option",
                    "kind": "product",
                    "fields": (),
                },
                *self.ir.types,
            ),
        )
        with self.assertRaisesRegex(GlyphError, "予約型名"):
            ImmediateAssemblyRuntime(bad_ir, INITIAL)


if __name__ == "__main__":
    unittest.main()

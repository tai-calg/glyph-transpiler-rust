from __future__ import annotations

from pathlib import Path
import unittest

from glyph import parse_compilation_model
from glyph.assembly_runtime import EffectInvocation, ImmediateAssemblyRuntime
from glyph.compiler import GlyphError


SOURCE = Path("examples/machine_assembly_immediate.glyph").read_text(encoding="utf-8")
INITIAL = {
    "door": {"mode": "DoorLocked"},
    "safety": {"mode": "SafetyNormal"},
    "motor": {"mode": "MotorRunning"},
}


class MachineAssemblyRuntimeTypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ir = parse_compilation_model(SOURCE).assembly_ir[0]

    def test_initial_state_type_is_checked(self) -> None:
        invalid = {**INITIAL, "door": "DoorLocked"}
        with self.assertRaisesRegex(GlyphError, "product型 'DoorState'"):
            ImmediateAssemblyRuntime(self.ir, invalid)

    def test_input_variant_is_checked(self) -> None:
        runtime = ImmediateAssemblyRuntime(self.ir, INITIAL)

        def handler(instance: str, input_name: str, value: object, state: object):
            if False:
                yield EffectInvocation("never")
            return state

        with self.assertRaisesRegex(GlyphError, "DoorInputのvariantではない"):
            runtime.react("door", "input", "NotADoorInput", handler)

    def test_effect_argument_type_is_checked(self) -> None:
        runtime = ImmediateAssemblyRuntime(self.ir, INITIAL)

        def handler(instance: str, input_name: str, value: object, state: object):
            yield EffectInvocation("notify_safety", "StopRequested")
            return state

        with self.assertRaisesRegex(GlyphError, "SafetyInputのvariantではない"):
            runtime.react("door", "input", "ForcedOpen", handler)

    def test_host_result_type_is_checked(self) -> None:
        runtime = ImmediateAssemblyRuntime(self.ir, INITIAL)

        def handler(instance: str, input_name: str, value: object, state: object):
            yield EffectInvocation("write_motor", "DisableMotor")
            return state

        def bad_host(instance: str, effect: str, arguments: tuple[object, ...]):
            return "not-a-receipt"

        with self.assertRaisesRegex(GlyphError, "product型 'Receipt'"):
            runtime.react("motor", "input", "StopRequested", handler, bad_host)

    def test_next_state_type_is_checked(self) -> None:
        runtime = ImmediateAssemblyRuntime(self.ir, INITIAL)

        def handler(instance: str, input_name: str, value: object, state: object):
            if False:
                yield EffectInvocation("never")
            return {"mode": "MotorRunning"}

        with self.assertRaisesRegex(GlyphError, "DoorModeのvariantではない"):
            runtime.react("door", "input", "ForcedOpen", handler)

    def test_generator_finally_runs_when_host_fails(self) -> None:
        runtime = ImmediateAssemblyRuntime(self.ir, INITIAL)
        closed: list[str] = []

        def handler(instance: str, input_name: str, value: object, state: object):
            try:
                yield EffectInvocation("write_motor", "DisableMotor")
                return state
            finally:
                closed.append(instance)

        def failing_host(instance: str, effect: str, arguments: tuple[object, ...]):
            raise RuntimeError("host failed")

        with self.assertRaisesRegex(RuntimeError, "host failed"):
            runtime.react("motor", "input", "StopRequested", handler, failing_host)
        self.assertEqual(closed, ["motor"])


if __name__ == "__main__":
    unittest.main()

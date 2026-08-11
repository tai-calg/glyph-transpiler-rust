from __future__ import annotations

from pathlib import Path
import unittest

from glyph import parse_compilation_model
from glyph.assembly_runtime import EffectInvocation, ImmediateAssemblyRuntime


INITIAL = {
    "door": {"mode": "DoorLocked"},
    "safety": {"mode": "SafetyNormal"},
    "motor": {"mode": "MotorRunning"},
}


class MachineAssemblyRuntimeFailureTests(unittest.TestCase):
    def test_host_failure_rolls_back_machine_states(self) -> None:
        source = Path("examples/machine_assembly_immediate.glyph").read_text(
            encoding="utf-8"
        )
        model = parse_compilation_model(source)
        runtime = ImmediateAssemblyRuntime(model.assembly_ir[0], INITIAL)

        def handler(instance: str, input_name: str, value: object, state: object):
            if instance == "door":
                state["mode"] = "DoorFaulted"
                yield EffectInvocation("notify_safety", "EmergencyDetected")
                return state
            if instance == "safety":
                state["mode"] = "SafetyEmergency"
                yield EffectInvocation("request_motor", "StopRequested")
                return state
            if instance == "motor":
                state["mode"] = "MotorStopped"
                yield EffectInvocation("write_motor", "DisableMotor")
                return state
            raise AssertionError(instance)

        def failing_host(
            instance: str,
            effect: str,
            arguments: tuple[object, ...],
        ) -> object:
            raise RuntimeError("motor bus unavailable")

        with self.assertRaisesRegex(RuntimeError, "motor bus unavailable"):
            runtime.react(
                "door",
                "input",
                "ForcedOpen",
                handler,
                failing_host,
            )

        self.assertEqual(runtime.states, INITIAL)

    def test_state_snapshots_do_not_expose_internal_mutable_values(self) -> None:
        source = Path("examples/machine_assembly_immediate.glyph").read_text(
            encoding="utf-8"
        )
        model = parse_compilation_model(source)
        runtime = ImmediateAssemblyRuntime(model.assembly_ir[0], INITIAL)

        leaked = runtime.states
        leaked["door"]["mode"] = "DoorFaulted"
        self.assertEqual(runtime.states["door"], {"mode": "DoorLocked"})


if __name__ == "__main__":
    unittest.main()

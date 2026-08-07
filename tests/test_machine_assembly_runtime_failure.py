from __future__ import annotations

from pathlib import Path
import unittest

from glyph import parse_compilation_model
from glyph.assembly_runtime import EffectInvocation, ImmediateAssemblyRuntime


INITIAL = {
    "door": "DoorLocked",
    "safety": "SafetyNormal",
    "motor": "MotorRunning",
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
                yield EffectInvocation("notify_safety", "EmergencyDetected")
                return "DoorFaulted"
            if instance == "safety":
                yield EffectInvocation("request_motor", "StopRequested")
                return "SafetyEmergency"
            if instance == "motor":
                yield EffectInvocation("write_motor", "DisableMotor")
                return "MotorStopped"
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


if __name__ == "__main__":
    unittest.main()

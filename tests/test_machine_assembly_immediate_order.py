from __future__ import annotations

from pathlib import Path
import unittest

from glyph import parse_compilation_model
from glyph.assembly_runtime import EffectInvocation, ImmediateAssemblyRuntime


class MachineAssemblyImmediateOrderTests(unittest.TestCase):
    def test_target_completes_before_source_resumes_after_effect(self) -> None:
        source = Path("examples/machine_assembly_immediate.glyph").read_text(
            encoding="utf-8"
        )
        model = parse_compilation_model(source)
        runtime = ImmediateAssemblyRuntime(
            model.assembly_ir[0],
            {
                "door": "DoorLocked",
                "safety": "SafetyNormal",
                "motor": "MotorRunning",
            },
        )
        order: list[str] = []

        def handler(instance: str, input_name: str, value: object, state: object):
            order.append(f"{instance}:enter")
            if instance == "door":
                order.append("door:before-notify")
                yield EffectInvocation("notify_safety", "EmergencyDetected")
                order.append("door:after-notify")
                next_state = "DoorFaulted"
            elif instance == "safety":
                order.append("safety:before-request")
                yield EffectInvocation("request_motor", "StopRequested")
                order.append("safety:after-request")
                next_state = "SafetyEmergency"
            elif instance == "motor":
                order.append("motor:before-write")
                receipt = yield EffectInvocation("write_motor", "DisableMotor")
                order.append(f"motor:receipt:{receipt}")
                order.append("motor:after-write")
                next_state = "MotorStopped"
            else:
                self.fail(instance)
            order.append(f"{instance}:exit")
            return next_state

        def host(instance: str, effect: str, arguments: tuple[object, ...]):
            return "Receipt"

        runtime.react("door", "input", "ForcedOpen", handler, host)

        self.assertEqual(
            order,
            [
                "door:enter",
                "door:before-notify",
                "safety:enter",
                "safety:before-request",
                "motor:enter",
                "motor:before-write",
                "motor:receipt:Receipt",
                "motor:after-write",
                "motor:exit",
                "safety:after-request",
                "safety:exit",
                "door:after-notify",
                "door:exit",
            ],
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import unittest

from glyph import parse_compilation_model
from glyph.assembly_runtime import EffectEmission, ImmediateAssemblyRuntime


class MachineAssemblyImmediateOrderTests(unittest.TestCase):
    def test_target_completes_before_source_resumes_after_effect(self) -> None:
        source = Path("examples/machine_assembly_immediate.glyph").read_text(
            encoding="utf-8"
        )
        model = parse_compilation_model(source)
        runtime = ImmediateAssemblyRuntime(model.assembly_ir[0])
        order: list[str] = []

        def handler(instance: str, input_name: str, value: object):
            order.append(f"{instance}:enter")
            if instance == "door":
                order.append("door:before-notify")
                yield EffectEmission("notify_safety", "EmergencyDetected")
                order.append("door:after-notify")
            elif instance == "safety":
                order.append("safety:before-request")
                yield EffectEmission("request_motor", "StopRequested")
                order.append("safety:after-request")
            elif instance == "motor":
                order.append("motor:before-write")
                yield EffectEmission("write_motor", "DisableMotor")
                order.append("motor:after-write")
            order.append(f"{instance}:exit")

        runtime.react("door", "input", "ForcedOpen", handler)

        self.assertEqual(
            order,
            [
                "door:enter",
                "door:before-notify",
                "safety:enter",
                "safety:before-request",
                "motor:enter",
                "motor:before-write",
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

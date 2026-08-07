from __future__ import annotations

import math
from pathlib import Path
from threading import Event, Thread
import unittest

from glyph import parse_compilation_model
from glyph.assembly_runtime import EffectInvocation, ImmediateAssemblyRuntime
from glyph.compiler import GlyphError


EXAMPLE = Path("examples/machine_assembly_immediate.glyph").read_text(
    encoding="utf-8"
)
INITIAL = {
    "door": {"mode": "DoorLocked"},
    "safety": {"mode": "SafetyNormal"},
    "motor": {"mode": "MotorRunning"},
}


def scalar_source(type_name: str) -> str:
    return f"""\
+Mode=Idle|Done|Fault
*State(mode:Mode)

>next(state:State,input:{type_name}):State=state

machine Scalar(state:State,input:{type_name})
  select=state.mode
  init=State(Idle)
  next=next(state,input)
  success=Done
  failure=Fault

assembly ScalarAssembly
  scalar=Scalar
"""


HOST_SOURCE = """\
+Input=Trigger
+Mode=Idle|Done|Fault
*State(mode:Mode)
*Payload(value:I)

!write(payload:Payload):()

>fire(state:State):State
  result := write(Payload(1))
  State(Done)

>next(state:State,input:Input):State
  input==Trigger>>fire(state)
  _>>state

machine Actor(state:State,input:Input)
  select=state.mode
  init=State(Idle)
  next=next(state,input)
  success=Done
  failure=Fault

assembly Single
  actor=Actor
"""


class AssemblyRuntimeHardeningV2Tests(unittest.TestCase):
    def test_ir_mapping_has_no_mutable_internal_storage(self) -> None:
        record = parse_compilation_model(EXAMPLE).assembly_ir[0].instances[0]
        self.assertIsInstance(record, tuple)
        self.assertFalse(hasattr(record, "_data"))
        with self.assertRaises(AttributeError):
            object.__setattr__(record, "_data", {})
        with self.assertRaises(TypeError):
            dict.__setitem__(record, "machine", "Other")
        self.assertEqual(record["machine"], "Door")

    def test_cross_thread_host_reentry_is_rejected_without_deadlock(self) -> None:
        runtime = ImmediateAssemblyRuntime(
            parse_compilation_model(EXAMPLE).assembly_ir[0], INITIAL
        )
        done = Event()
        errors: list[BaseException] = []

        def handler(instance, input_name, value, state):
            receipt = yield EffectInvocation("write_motor", "DisableMotor")
            self.assertEqual(receipt, {"command": "DisableMotor"})
            return {"mode": "MotorStopped"}

        def host(instance, effect, arguments):
            def compete():
                try:
                    runtime.react(
                        "motor",
                        "input",
                        "StopRequested",
                        handler,
                        host,
                    )
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    done.set()

            worker = Thread(target=compete)
            worker.start()
            self.assertTrue(done.wait(1.0), "competing react() deadlocked")
            worker.join(1.0)
            self.assertFalse(worker.is_alive())
            return {"command": arguments[0]}

        result = runtime.react(
            "motor", "input", "StopRequested", handler, host
        )
        self.assertEqual(result.states["motor"], {"mode": "MotorStopped"})
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], GlyphError)
        self.assertIn("再入・並行実行は禁止", str(errors[0]))

    def test_numeric_ranges_and_finite_values(self) -> None:
        def handler(instance, input_name, value, state):
            if False:
                yield EffectInvocation("never")
            return state

        u8 = ImmediateAssemblyRuntime(
            parse_compilation_model(scalar_source("u8")).assembly_ir[0],
            {"scalar": {"mode": "Idle"}},
        )
        u8.react("scalar", "input", 0, handler)
        u8.react("scalar", "input", 255, handler)
        for value in (-1, 256):
            with self.assertRaisesRegex(GlyphError, "u8の範囲外"):
                u8.react("scalar", "input", value, handler)

        f32 = ImmediateAssemblyRuntime(
            parse_compilation_model(scalar_source("f32")).assembly_ir[0],
            {"scalar": {"mode": "Idle"}},
        )
        f32.react("scalar", "input", 3.4e38, handler)
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaisesRegex(GlyphError, "有限値"):
                f32.react("scalar", "input", value, handler)
        with self.assertRaisesRegex(GlyphError, "f32の表現範囲外"):
            f32.react("scalar", "input", 3.5e38, handler)

    def test_host_argument_audit_snapshot_precedes_host_mutation(self) -> None:
        runtime = ImmediateAssemblyRuntime(
            parse_compilation_model(HOST_SOURCE).assembly_ir[0],
            {"actor": {"mode": "Idle"}},
        )

        def handler(instance, input_name, value, state):
            yield EffectInvocation("write", {"value": 1})
            return {"mode": "Done"}

        def host(instance, effect, arguments):
            arguments[0]["value"] = 99
            return None

        result = runtime.react(
            "actor", "input", "Trigger", handler, host
        )
        self.assertEqual(
            result.external_effects[0].arguments,
            ({"value": 1},),
        )


if __name__ == "__main__":
    unittest.main()

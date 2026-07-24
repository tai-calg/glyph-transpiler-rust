from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.host_runtime import (
    HostBindingError,
    HostGlyphProgram,
    HostInvocationError,
)
from glyph.pure_runtime import ResultValue, VariantValue


PUMP_SOURCE = """\
machine Pump(state:PumpState,event:PumpEvent,input:PumpInput)
  select=state.mode
  init=PumpState(PumpOff,PumpReceipt(false))
  next=pump_step(state,event,input)
  success=PumpOn
  failure=PumpFault

+PumpEvent=PumpNone|PumpStart|PumpStop
+PumpMode=PumpOff|PumpOn|PumpFault
+WriteError=WriteFailed
*PumpInput(enable:B)
*PumpReceipt(enabled:B)
*PumpState(mode:PumpMode,receipt:PumpReceipt)

!write_pump(enabled:B):PumpReceipt|WriteError

>apply_pump(enabled:B):PumpReceipt|WriteError=write_pump(enabled)

>pump_step(state:PumpState,event:PumpEvent,input:PumpInput):PumpState|WriteError
  state.mode==PumpOff&event==PumpStart >> Ok(PumpState(PumpOn,apply_pump(input.enable)?))
  state.mode==PumpOn&event==PumpStop >> Ok(PumpState(PumpOff,apply_pump(false)?))
  _ >> Ok(state)
"""


ORDER_SOURCE = """\
+EffectError=EffectFailed
*Ack(value:B)
*Pair(first:Ack,second:Ack)

!first_effect(value:B):Ack|EffectError
!second_effect(value:B):Ack|EffectError

>run(value:B):Pair|EffectError=Ok(Pair(first_effect(value)?,second_effect(value)?))
"""


def pump_arguments():
    return {
        "state": {
            "mode": VariantValue("PumpMode", "PumpOff"),
            "receipt": {"enabled": False},
        },
        "event": VariantValue("PumpEvent", "PumpStart"),
        "input": {"enable": True},
    }


class HostRuntimeTests(unittest.TestCase):
    def compile_pump(self):
        return CompilationPipeline().compile_text(
            PUMP_SOURCE,
            source_name="pump-runtime.glyph",
        ).model

    def test_successful_effect_drives_machine_to_normal_target(self) -> None:
        model = self.compile_pump()
        program = HostGlyphProgram(
            model,
            bindings={
                "write_pump": lambda enabled: ResultValue(
                    True,
                    {"enabled": enabled},
                )
            },
        )

        result = program.invoke_machine("Pump", pump_arguments())

        self.assertEqual(result.source_state, "PumpOff")
        self.assertEqual(result.target_state, "PumpOn")
        self.assertEqual(result.outcome, "success")
        self.assertIsNone(result.failure_type)
        self.assertEqual(result.invocation_ids, ("H1",))
        self.assertEqual(result.invocations[0].effect, "write_pump")
        self.assertTrue(result.invocations[0].succeeded)

    def test_declared_failure_drives_machine_to_failure_target(self) -> None:
        model = self.compile_pump()
        program = HostGlyphProgram(
            model,
            bindings={
                "write_pump": lambda enabled: ResultValue(
                    False,
                    VariantValue("WriteError", "WriteFailed"),
                )
            },
        )

        result = program.invoke_machine("Pump", pump_arguments())

        self.assertEqual(result.source_state, "PumpOff")
        self.assertEqual(result.target_state, "PumpFault")
        self.assertEqual(result.outcome, "failure")
        self.assertEqual(result.failure_type, "WriteError")
        self.assertEqual(result.invocation_ids, ("H1",))
        self.assertFalse(result.invocations[0].succeeded)

    def test_unregistered_effect_is_rejected(self) -> None:
        program = HostGlyphProgram(self.compile_pump())
        with self.assertRaisesRegex(HostBindingError, "no registered Host binding"):
            program.invoke_machine("Pump", pump_arguments())

    def test_binding_arity_is_checked_at_registration(self) -> None:
        program = HostGlyphProgram(self.compile_pump())
        with self.assertRaisesRegex(HostBindingError, "exactly 1 positional"):
            program.bind("write_pump", lambda: None)

    def test_python_exception_is_not_converted_to_glyph_failure(self) -> None:
        def explode(enabled):
            raise OSError("device unavailable")

        program = HostGlyphProgram(
            self.compile_pump(),
            bindings={"write_pump": explode},
        )
        with self.assertRaisesRegex(
            HostInvocationError,
            "Python exceptions are not converted",
        ):
            program.invoke_machine("Pump", pump_arguments())

    def test_binding_result_type_is_checked(self) -> None:
        program = HostGlyphProgram(
            self.compile_pump(),
            bindings={"write_pump": lambda enabled: ResultValue(True, "bad")},
        )
        with self.assertRaisesRegex(HostInvocationError, "outside its declared type"):
            program.invoke_machine("Pump", pump_arguments())

    def test_multiple_effects_execute_in_source_order(self) -> None:
        model = CompilationPipeline().compile_text(
            ORDER_SOURCE,
            source_name="ordered-host.glyph",
        ).model
        calls = []

        def first(value):
            calls.append("first")
            return ResultValue(True, {"value": value})

        def second(value):
            calls.append("second")
            return ResultValue(True, {"value": value})

        program = HostGlyphProgram(
            model,
            bindings={"first_effect": first, "second_effect": second},
        )
        value = program.invoke("run", {"value": True})

        self.assertTrue(value.ok)
        self.assertEqual(calls, ["first", "second"])
        self.assertEqual(
            [item.effect for item in program.last_invocations],
            ["first_effect", "second_effect"],
        )
        self.assertEqual(
            [item.invocation_id for item in program.last_invocations],
            ["H1", "H2"],
        )


if __name__ == "__main__":
    unittest.main()

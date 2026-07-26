from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views


SOURCE = """\
machine Pump(state:PumpState,event:PumpEvent,input:PumpInput)
  select=state.mode
  init=PumpState(PumpOff,PumpReceipt(false))
  next=pump_step(state,event,input)
  success=PumpOff
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


class HostInvocationIRTests(unittest.TestCase):
    def compile_views(self):
        output = CompilationPipeline().compile_text(SOURCE, source_name="pump-host.glyph")
        return build_io_state_views(output.model, output.diagrams.ir)

    def test_effect_call_sites_are_structured_once(self) -> None:
        views = self.compile_views()
        ir = views["host_invocation_ir"]
        self.assertEqual(ir["schema"], "glyph.host-invocation-ir")
        self.assertEqual(ir["version"], 1)
        self.assertEqual(len(ir["invocations"]), 1)

        invocation = ir["invocations"][0]
        self.assertEqual(invocation["id"], "H1")
        self.assertEqual(invocation["caller"], "apply_pump")
        self.assertEqual(invocation["effect"], "write_pump")
        self.assertEqual(invocation["call"], "write_pump(enabled)")
        self.assertEqual(
            invocation["arguments"],
            [{"expression": "enabled", "parameter": "enabled", "type": "bool"}],
        )
        self.assertEqual(invocation["success_type"], "PumpReceipt")
        self.assertEqual(invocation["failure_type"], "WriteError")
        self.assertEqual(invocation["result_type"], "R<PumpReceipt,WriteError>")

    def test_transitions_reference_call_site_and_use_specialized_arguments(self) -> None:
        views = self.compile_views()
        machine = views["state"]["machines"][0]

        normal = next(
            item
            for item in machine["transitions"]
            if item["source_state"] == "PumpOff"
            and item["target_state"] == "PumpOn"
            and item.get("event") == "PumpStart"
            and not item.get("synthesized_failure")
        )
        failure = next(
            item
            for item in machine["transitions"]
            if item["source_state"] == "PumpOff"
            and item["target_state"] == "PumpFault"
            and item.get("event") == "PumpStart"
            and item.get("synthesized_failure")
        )

        self.assertEqual(normal["action"], "write_pump(input.enable)")
        self.assertEqual(normal["action_invocation_ids"], ["H1"])
        self.assertEqual(failure["action"], "write_pump(input.enable)")
        self.assertEqual(failure["failure_type"], "WriteError")
        self.assertEqual(failure["action_invocation_ids"], ["H1"])
        self.assertEqual(
            failure["display_label"],
            "PumpStart / write_pump(input.enable) | WriteError",
        )
        self.assertEqual(machine["analysis"]["unresolved_host_invocation_count"], 0)
        self.assertGreaterEqual(machine["analysis"]["host_invocation_link_count"], 2)


if __name__ == "__main__":
    unittest.main()

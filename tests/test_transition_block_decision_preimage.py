from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views


def output_display(item: dict[str, object]) -> str:
    emitted = item.get("emitted_output")
    if not isinstance(emitted, dict):
        return ""
    return str(emitted.get("display") or emitted.get("expression") or "")


class TransitionBlockDecisionPreimageTests(unittest.TestCase):
    def test_final_conditional_binding_is_resolved_through_prior_pure_bindings(self) -> None:
        source = """\
machine Motor(state:MotorState,input:Input)
  select=state.mode
  action=state.command
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted

*Input(raw:F,enabled:B)
+Command=Stop|Drive(F)
+Mode=Stopped|Running|Faulted
*MotorState(mode:Mode,command:Command)

>decide(input:Input):Command
  normalized :=
    input.raw
    /> |x| min(x,1.0)
  command :=
    !input.enabled >> Stop
    _ >> Drive(normalized)
  command

>step(state:MotorState,input:Input):MotorState
  command := decide(input)
  next :=
    command==Stop >> MotorState(Stopped,Stop)
    command==Drive(speed) >> MotorState(Running,Drive(speed))
    _ >> state
  next
"""
        output = CompilationPipeline().compile_text(source, source_name="block-decision.glyph")
        views = build_io_state_views(output.model, output.diagrams.ir)
        machine = views["state"]["machines"][0]

        self.assertEqual(machine["analysis"]["unresolved_input_preimage_count"], 0)
        self.assertGreater(machine["analysis"]["expanded_input_preimage_count"], 0)
        self.assertNotIn(
            "STIR_INPUT_PREIMAGE_UNRESOLVED",
            {item["code"] for item in machine["diagnostics"]},
        )

        stop = next(
            item
            for item in machine["transitions"]
            if output_display(item) == "Stop" and not item.get("synthesized_failure")
        )
        self.assertEqual(stop["trigger"]["display"], "!input.enabled")
        self.assertEqual(stop["trigger"]["decision_function"], "decide")
        self.assertIsNone(stop["action"])

        drive = next(
            item
            for item in machine["transitions"]
            if item.get("target_state") == "Running" and not item.get("synthesized_failure")
        )
        self.assertEqual(drive["trigger"]["display"], "otherwise")
        self.assertEqual(drive["trigger"]["decision_function"], "decide")
        self.assertNotIn("__glyph_block_", drive["trigger"]["dataflow_path"])
        self.assertEqual(output_display(drive), "Drive(min(input.raw,1.0))")
        self.assertIsNone(drive["action"])
        self.assertNotEqual(output_display(drive), drive["target_state"])


if __name__ == "__main__":
    unittest.main()

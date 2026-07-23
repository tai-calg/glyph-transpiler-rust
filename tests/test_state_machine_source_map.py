from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views


SOURCE = """\
machine Motor(state:MotorState,input:Input)
  select=state.mode
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted

@EXPAND
  value := input.raw
@end

*Input(raw:F)
+Command=Stop|Drive(F)
+Mode=Stopped|Running|Faulted
*MotorState(mode:Mode,command:Command)

>step(state:MotorState,input:Input):MotorState
  command := Stop
  next :=
    command==Stop >> MotorState(Stopped,Stop)
    command==Drive(speed) >> MotorState(Running,Drive(speed))
    _ >> MotorState(Faulted,Stop)
  next
"""


class StateMachineSourceMapTests(unittest.TestCase):
    def test_generated_guard_lines_are_remapped_to_glyph_source(self) -> None:
        outputs = CompilationPipeline().compile_text(SOURCE, source_name="source-map.glyph")
        views = build_io_state_views(outputs.model, outputs.diagrams.ir)
        machine = views["state"]["machines"][0]
        lines = SOURCE.splitlines()
        stop_line = next(i for i, text in enumerate(lines, 1) if "command==Stop" in text)
        drive_line = next(i for i, text in enumerate(lines, 1) if "command==Drive" in text)
        fallback_line = next(i for i, text in enumerate(lines, 1) if "_ >> MotorState(Faulted" in text)

        self.assertEqual(machine["unreachable_branches"], [fallback_line])
        warning = next(
            item
            for item in machine["diagnostics"]
            if item["code"] == "unreachable-branch"
        )
        self.assertEqual(warning["line"], fallback_line)
        transition_lines = {
            transition["source"]["line"] for transition in machine["transitions"]
        }
        self.assertEqual(transition_lines, {stop_line, drive_line})
        self.assertTrue(all(line <= len(lines) for line in transition_lines))


if __name__ == "__main__":
    unittest.main()

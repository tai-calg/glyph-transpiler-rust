from __future__ import annotations

import unittest

from glyph import parse_compilation_model
from glyph.compiler import GlyphError


BASE = """\
+SourceInput=Trigger
+SourceMode=SourceIdle|SourceDone|SourceFault
*SourceState(mode:SourceMode)

+TargetInput=Notice
+TargetMode=TargetIdle|TargetDone|TargetFault
*TargetState(mode:TargetMode)

!notify(event:TargetInput):TargetInput=event

>source_fire(state:SourceState):SourceState
  notice := notify(Notice)
  SourceState(SourceDone)

>source_next(state:SourceState,input:SourceInput):SourceState
  input==Trigger>>source_fire(state)
  _>>state

>target_next(state:TargetState,input:TargetInput):TargetState
  input==Notice>>TargetState(TargetDone)
  _>>state

machine Source(state:SourceState,input:SourceInput)
  select=state.mode
  init=SourceState(SourceIdle)
  next=source_next(state,input)
  success=SourceDone
  failure=SourceFault

machine Target(state:TargetState,input:TargetInput)
  select=state.mode
  init=TargetState(TargetIdle)
  next=target_next(state,input)
  success=TargetDone
  failure=TargetFault

assembly Connected
  source=Source
  target=Target

  source.notify -> target.input
"""


class MachineAssemblyRouteConstraintTests(unittest.TestCase):
    def test_internal_route_requires_inline_effect_body(self) -> None:
        source = BASE.replace(
            "!notify(event:TargetInput):TargetInput=event",
            "!notify(event:TargetInput):TargetInput",
        )
        with self.assertRaisesRegex(GlyphError, "本体が必要"):
            parse_compilation_model(source)

    def test_immediate_route_target_has_one_input_parameter(self) -> None:
        source = BASE.replace(
            "machine Target(state:TargetState,input:TargetInput)",
            "machine Target(state:TargetState,input:TargetInput,context:B)",
        )
        with self.assertRaisesRegex(GlyphError, "入力parameterを1つだけ"):
            parse_compilation_model(source)


if __name__ == "__main__":
    unittest.main()

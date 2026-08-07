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

!notify(event:TargetInput):()

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


BUILTIN_TYPE_EQUIVALENCE = """\
+SourceMode=SourceIdle|SourceDone|SourceFault
*SourceState(mode:SourceMode)

+TargetMode=TargetIdle|TargetDone|TargetFault
*TargetState(mode:TargetMode)

!notify(event:O<S>):()

>source_fire(input:O<S>):SourceState
  value := notify(input)
  SourceState(SourceDone)

>source_next(state:SourceState,input:O<S>):SourceState=source_fire(input)
>target_next(state:TargetState,input:Option<String>):TargetState=TargetState(TargetDone)

machine Source(state:SourceState,input:O<S>)
  select=state.mode
  init=SourceState(SourceIdle)
  next=source_next(state,input)
  success=SourceDone
  failure=SourceFault

machine Target(state:TargetState,input:Option<String>)
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
    def test_internal_route_rejects_host_prototype_body(self) -> None:
        source = BASE.replace(
            "!notify(event:TargetInput):()",
            "!notify(event:TargetInput):()=notify(event)",
        )
        with self.assertRaisesRegex(GlyphError, "Host試作本体を持てない"):
            parse_compilation_model(source)

    def test_immediate_route_target_has_one_input_parameter(self) -> None:
        source = BASE.replace(
            "machine Target(state:TargetState,input:TargetInput)",
            "machine Target(state:TargetState,input:TargetInput,context:B)",
        )
        with self.assertRaisesRegex(GlyphError, "入力parameterを1つだけ"):
            parse_compilation_model(source)

    def test_effect_used_only_in_guard_is_not_a_routable_transition_action(self) -> None:
        source = BASE.replace(
            "!notify(event:TargetInput):()",
            "!notify(event:TargetInput):()\n"
            "!probe(event:TargetInput):B",
        ).replace(
            "input==Trigger>>source_fire(state)",
            "probe(Notice)>>source_fire(state)",
        ).replace(
            "source.notify -> target.input",
            "source.probe -> target.input",
        )
        with self.assertRaisesRegex(GlyphError, "遷移Actionから到達できない"):
            parse_compilation_model(source)

    def test_nested_inline_effect_remains_in_source_action_chain(self) -> None:
        source = BASE.replace(
            "!notify(event:TargetInput):()",
            "!notify(event:TargetInput):()\n"
            "!forward(event:TargetInput):()=notify(event)",
        ).replace(
            "notice := notify(Notice)",
            "notice := forward(Notice)",
        )
        model = parse_compilation_model(source)
        self.assertEqual(model.assembly_ir[0].routes[0]["effect"], "notify")

    def test_builtin_short_and_long_type_names_are_route_equivalent(self) -> None:
        model = parse_compilation_model(BUILTIN_TYPE_EQUIVALENCE)
        route = model.assembly_ir[0].routes[0]
        self.assertEqual(route["payload_type"], "O<S>")
        self.assertEqual(route["target_machine"], "Target")


if __name__ == "__main__":
    unittest.main()

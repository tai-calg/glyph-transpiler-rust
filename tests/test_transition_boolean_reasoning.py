from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views
from glyph.state_transition_contract import (
    RAW_STATE_TRANSITION_IR_VERSION,
    STATE_TRANSITION_IR_VERSION,
)
from glyph.transition_semantics import (
    STATE_TRANSITION_IR_VERSION as FACADE_VERSION,
)


def compile_source(source: str) -> dict[str, object]:
    output = CompilationPipeline().compile_text(source, source_name="boolean.glyph")
    return build_io_state_views(output.model, output.diagrams.ir)


SOURCE = """machine Example(state:State,input:Input)
  select=state.mode
  init=State(A)
  next=step(state,input)
  success=B
  failure=C

*Input(x:B)
+Mode=A|B|C
*State(mode:Mode)

>step(state:State,input:Input):State
  state.mode==A&(input.x|!input.x) >> State(B)
  state.mode==B&input.x&!input.x >> State(C)
  _ >> state
"""


class TransitionBooleanReasoningTests(unittest.TestCase):
    def test_tautology_exhausts_source_before_wildcard(self) -> None:
        views = compile_source(SOURCE)
        machine = views["state"]["machines"][0]
        pairs = {
            (item["source_state"], item["target_state"])
            for item in machine["transitions"]
            if not item.get("synthesized_failure")
        }
        self.assertIn(("A", "B"), pairs)
        self.assertNotIn(("A", "A"), pairs)

    def test_contradiction_is_removed_before_fallback(self) -> None:
        views = compile_source(SOURCE)
        machine = views["state"]["machines"][0]
        pairs = {
            (item["source_state"], item["target_state"])
            for item in machine["transitions"]
            if not item.get("synthesized_failure")
        }
        self.assertNotIn(("B", "C"), pairs)
        self.assertIn(("B", "B"), pairs)

    def test_public_and_raw_versions_have_distinct_single_contract_markers(self) -> None:
        views = compile_source(SOURCE)
        machine = views["state"]["machines"][0]
        self.assertEqual(FACADE_VERSION, STATE_TRANSITION_IR_VERSION)
        self.assertEqual(STATE_TRANSITION_IR_VERSION, 5)
        self.assertEqual(
            views["state_transition_ir"],
            {
                "schema": "glyph.state-transition-ir",
                "version": STATE_TRANSITION_IR_VERSION,
                "stage": "public",
            },
        )
        self.assertEqual(machine["transition_ir"], views["state_transition_ir"])
        self.assertEqual(
            views["raw_state_transition_ir"]["version"],
            RAW_STATE_TRANSITION_IR_VERSION,
        )
        self.assertEqual(views["raw_state_transition_ir"]["stage"], "normalized-machine")


if __name__ == "__main__":
    unittest.main()

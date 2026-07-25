from __future__ import annotations

import json
import unittest

from glyph import compile_outputs, parse_compilation_model
from glyph.execution_ir import build_execution_structure_ir
from glyph.type_algebra import build_machine_coverage, build_type_algebra_ir


REACHABILITY_SOURCE = """
resource Token[Ready]
+Mode=Idle|Running|Stopped|Faulted
+Event=Advance|Hold
*State(mode:Mode)

>step(state:State,event:Event):State
  state.mode==Idle >> State(Running)
  state.mode==Running >> State(Stopped)
  _ >> state

machine Controller(state:State,event:Event)
  select=state.mode
  init=State(Idle)
  next=step(state,event)
  success=Stopped
  failure=Faulted
""".lstrip()


UNKNOWN_SOURCE = """
resource Token[Ready]
+Mode=Idle|Hidden
+Event=Tick
*State(mode:Mode,count:u64)

>step(state:State,event:Event):State
  state.count>0 >> State(Hidden,0)
  _ >> state

machine Controller(state:State,event:Event)
  select=state.mode
  init=State(Idle,0)
  next=step(state,event)
  success=Hidden
  failure=Idle
""".lstrip()


REJECTION_SOURCE = """
resource Token[Ready]
+Mode=Locked|Unlocked
+Event=Open
+Error=NotAllowed
*State(mode:Mode)

>step(state:State,event:Event):State|Error
  state.mode==Locked >> Err(NotAllowed)
  _ >> Ok(state)

machine Door(state:State,event:Event)
  select=state.mode
  init=State(Locked)
  next=step(state,event)
  success=Unlocked
  failure=Locked
""".lstrip()


def _coverage(source: str):
    model = parse_compilation_model(source, "state-reachability.glyph")
    execution = build_execution_structure_ir(
        model.preprocess.source,
        "state-reachability.glyph",
        model.expanded.program,
        model.expanded.specs,
        model.expanded.machines,
    )
    algebra = build_type_algebra_ir(
        "state-reachability.glyph",
        model.expanded.program,
    )
    return build_machine_coverage(
        model.expanded.program,
        model.expanded.machines,
        execution,
        algebra,
    )


class MachineStateReachabilityTests(unittest.TestCase):
    def test_init_graph_distinguishes_reachable_and_unreachable_states(self) -> None:
        coverage = _coverage(REACHABILITY_SOURCE)
        state = coverage[0].state_reachability
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.initial_state, "Idle")
        self.assertEqual(
            state.definitely_reachable,
            ("Idle", "Running", "Stopped"),
        )
        self.assertEqual(state.maybe_reachable, ())
        self.assertEqual(state.definitely_unreachable, ("Faulted",))
        self.assertTrue(state.exact)

    def test_tooling_json_contains_state_graph_and_warning(self) -> None:
        outputs = compile_outputs(REACHABILITY_SOURCE, "state-reachability.glyph")
        payload = json.loads(outputs.diagrams.files["type-algebra-tooling.json"])
        state = payload["machine_state_reachability"][0]
        self.assertEqual(state["initial_state"], "Idle")
        self.assertEqual(state["definitely_unreachable"], ["Faulted"])
        codes = {item["code"] for item in payload["diagnostics"]}
        self.assertIn("machine-state-unreachable", codes)

    def test_unknown_transition_creates_possible_edges_not_false_warning(self) -> None:
        outputs = compile_outputs(UNKNOWN_SOURCE, "unknown-state.glyph")
        payload = json.loads(outputs.diagrams.files["type-algebra-tooling.json"])
        state = payload["machine_state_reachability"][0]
        self.assertFalse(state["exact"])
        self.assertEqual(state["definitely_unreachable"], [])
        self.assertIn("Hidden", state["maybe_reachable"])
        codes = {item["code"] for item in payload["diagnostics"]}
        self.assertNotIn("machine-state-unreachable", codes)

    def test_explicit_rejection_is_no_edge_not_a_guard_error(self) -> None:
        outputs = compile_outputs(REJECTION_SOURCE, "rejection-state.glyph")
        payload = json.loads(outputs.diagrams.files["type-algebra-tooling.json"])
        coverage = payload["machine_coverage"][0]
        self.assertEqual(coverage["rejected_pairs"], 1)
        state = payload["machine_state_reachability"][0]
        self.assertEqual(state["definitely_reachable"], ["Locked"])
        self.assertEqual(state["definitely_unreachable"], ["Unlocked"])
        codes = {item["code"] for item in payload["diagnostics"]}
        self.assertIn("machine-state-unreachable", codes)
        self.assertNotIn("machine-coverage-unreachable", codes)


if __name__ == "__main__":
    unittest.main()

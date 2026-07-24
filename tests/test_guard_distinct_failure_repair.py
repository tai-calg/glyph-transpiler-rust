from __future__ import annotations

import unittest
from pathlib import Path

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views
from glyph.transition_semantics_runtime import enrich_runtime_io_state_views


ROOT = Path(__file__).resolve().parents[1]


class GuardDistinctFailureRepairTests(unittest.TestCase):
    def test_same_effect_call_under_distinct_guards_keeps_both_failure_edges(self) -> None:
        path = ROOT / "examples/state_diagrams/cooling_fan_effect.glyph"
        output = CompilationPipeline().compile_text(
            path.read_text(encoding="utf-8"),
            source_name=str(path),
        )
        views = enrich_runtime_io_state_views(
            output.model,
            build_io_state_views(output.model, output.diagrams.ir),
        )
        machine = views["state"]["machines"][0]

        failures = [
            transition
            for transition in machine["transitions"]
            if transition["source_state"] == "FanRunning"
            and transition["target_state"] == "FanFault"
            and transition.get("synthesized_failure")
            and transition.get("action") == "write_fan(0.0) ! FanWriteError"
        ]
        self.assertEqual(
            {transition.get("guard") for transition in failures},
            {"input.overheat", "!input.enable"},
        )
        self.assertEqual(
            machine["analysis"]["guard_distinct_failure_repair_count"],
            1,
        )
        self.assertEqual(
            machine["analysis"]["synthesized_failure_transition_count"],
            5,
        )


if __name__ == "__main__":
    unittest.main()

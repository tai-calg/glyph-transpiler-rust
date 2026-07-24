from __future__ import annotations

import unittest
from pathlib import Path

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views
from glyph.transition_semantics_runtime import enrich_runtime_io_state_views


ROOT = Path(__file__).resolve().parents[1]


class NestedTransitionRepairTests(unittest.TestCase):
    def test_nested_state_helper_restores_outer_event_and_removes_stale_warning(self) -> None:
        path = ROOT / "examples/state_diagrams/valve_nested_effect.glyph"
        output = CompilationPipeline().compile_text(
            path.read_text(encoding="utf-8"),
            source_name=str(path),
        )
        views = enrich_runtime_io_state_views(
            output.model,
            build_io_state_views(output.model, output.diagrams.ir),
        )
        machine = views["state"]["machines"][0]

        self.assertTrue(
            any(
                transition["source_state"] == "ValveClosed"
                and transition["target_state"] == "ValveOpen"
                and transition.get("event") == "ValveOpenRequest"
                and transition.get("action") == "write_valve(true)"
                for transition in machine["transitions"]
            )
        )
        self.assertNotIn(
            "state-independent-transition",
            {item["code"] for item in machine["diagnostics"]},
        )
        self.assertEqual(
            views["summary"]["state_warnings"],
            sum(
                len(item["diagnostics"])
                for item in views["state"]["machines"]
            ),
        )


if __name__ == "__main__":
    unittest.main()

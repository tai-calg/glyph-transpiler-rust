from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from glyph.live_image import LiveImage
from glyph.live_studio import LiveGlyphStudio
from glyph.live_studio_ui import LIVE_STUDIO_HTML


def function_design(value: str = "1", return_type: str = "U") -> dict[str, object]:
    return {
        "symbols": [
            {
                "id": "fn",
                "name": "inc",
                "kind": "function",
                "line": 1,
                "type": f"Fn<U,{return_type}>",
            },
            {
                "id": "x",
                "name": "x",
                "kind": "parameter",
                "line": 1,
                "type": "U",
            },
        ],
        "functions": [
            {
                "symbol_id": "fn",
                "name": "inc",
                "params": ["x"],
                "return_type": return_type,
                "body": {
                    "kind": "number",
                    "type": return_type,
                    "value": value,
                    "line": 1,
                    "children": [],
                },
                "recursion": {
                    "recursive": False,
                    "analysis": "none",
                    "cycle": [],
                },
                "line": 1,
            }
        ],
        "machines": [],
        "raw_macros": [],
    }


class LiveImageTests(unittest.TestCase):
    def test_function_body_hot_swap_keeps_old_world_lease(self) -> None:
        image = LiveImage()
        image.stage(
            function_design("1"),
            source_digest="source-1",
            generated_code="code-1",
        )
        lease = image.acquire()
        self.assertEqual(lease.world.version, 1)

        state = image.stage(
            function_design("2"),
            source_digest="source-2",
            generated_code="code-2",
        )

        self.assertEqual(state["active_world"]["version"], 2)
        self.assertIsNone(state["pending_patch"])
        self.assertEqual(lease.world.version, 1)
        self.assertEqual(state["leases"], [{"world": 1, "count": 1}])
        cell = next(
            item
            for item in state["definition_cells"]
            if item["id"] == "function:inc"
        )
        self.assertEqual([item["world"] for item in cell["history"]], [1, 2])
        lease.release()

    def test_contract_change_waits_for_quiescence(self) -> None:
        image = LiveImage()
        base = {
            **function_design(),
            "runtime_contracts": {
                "worlds": [
                    {
                        "name": "Worker",
                        "locus": "Worker",
                        "region": ["App"],
                        "line": 2,
                    }
                ],
                "protocols": [],
                "handlers": [],
                "laws": [],
                "applications": [],
            },
        }
        changed = json.loads(json.dumps(base))
        changed["runtime_contracts"]["worlds"][0]["region"] = ["App", "Task"]
        image.stage(base, source_digest="source-1", generated_code="code-1")
        lease = image.acquire()

        state = image.stage(
            changed,
            source_digest="source-2",
            generated_code="code-2",
        )

        self.assertEqual(state["active_world"]["version"], 1)
        self.assertEqual(state["pending_patch"]["maximum_safety"], "quiescence")
        lease.release()
        self.assertEqual(image.to_dict()["active_world"]["version"], 2)
        self.assertIsNone(image.to_dict()["pending_patch"])

    def test_resource_change_requires_migration_plan(self) -> None:
        image = LiveImage()
        base = {
            **function_design(),
            "capabilities": {
                "resources": [
                    {
                        "name": "Buffer",
                        "type_parameters": [],
                        "states": ["Ready"],
                        "line": 2,
                    }
                ],
                "functions": [],
                "aggregates": [],
                "operations": [],
            },
        }
        changed = json.loads(json.dumps(base))
        changed["capabilities"]["resources"][0]["states"].append("Done")
        image.stage(base, source_digest="source-1", generated_code="code-1")

        state = image.stage(
            changed,
            source_digest="source-2",
            generated_code="code-2",
        )

        self.assertEqual(state["active_world"]["version"], 1)
        self.assertIn(
            "migration-plan-required",
            state["pending_patch"]["blockers"],
        )
        with self.assertRaisesRegex(RuntimeError, "migration plan"):
            image.commit_pending()
        committed = image.commit_pending(
            migration_plan="No live Buffer values in the bootstrap demo"
        )
        self.assertEqual(committed["active_world"]["version"], 2)

    def test_reader_change_requires_next_read_generation_acknowledgement(self) -> None:
        image = LiveImage()
        base = {
            **function_design(),
            "raw_macros": [{"name": "WHEN", "body": "old", "line": 1}],
        }
        changed = {
            **function_design(),
            "raw_macros": [{"name": "WHEN", "body": "new", "line": 1}],
        }
        image.stage(base, source_digest="source-1", generated_code="code-1")
        state = image.stage(
            changed,
            source_digest="source-2",
            generated_code="code-2",
        )
        self.assertIn(
            "reader-generation-acknowledgement-required",
            state["pending_patch"]["blockers"],
        )
        with self.assertRaisesRegex(RuntimeError, "reader"):
            image.commit_pending()
        committed = image.commit_pending(reader_acknowledged=True)
        self.assertEqual(committed["active_world"]["version"], 2)

    def test_compile_error_keeps_last_committed_world(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.glyph"
            source.write_text(">inc(x:U):U=x+1\n", encoding="utf-8")
            studio = LiveGlyphStudio(source)
            first = studio.rebuild()
            self.assertEqual(first.status, "ready")
            self.assertEqual(
                studio.state_dict()["live_image"]["active_world"]["version"],
                1,
            )

            second = studio.preview_source(">inc(x:U):U=\n")

            self.assertEqual(second.status, "error")
            state = studio.state_dict()
            self.assertEqual(state["live_image"]["active_world"]["version"], 1)
            self.assertIn("live-image.json", state["artifact_names"])

    def test_studio_preview_hot_swaps_completed_function(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.glyph"
            source.write_text(">inc(x:U):U=x+1\n", encoding="utf-8")
            studio = LiveGlyphStudio(source)
            studio.rebuild()

            snapshot = studio.preview_source(">inc(x:U):U=x+2\n")

            self.assertEqual(snapshot.status, "ready")
            state = studio.state_dict()["live_image"]
            self.assertEqual(state["active_world"]["version"], 2)
            self.assertIsNone(state["pending_patch"])

    def test_live_ui_injection_is_present(self) -> None:
        for marker in (
            "Live Image",
            "function liveImageView",
            "/api/live/commit",
            "/api/live/discard",
            "migration-plan-required",
        ):
            self.assertIn(marker, LIVE_STUDIO_HTML)


if __name__ == "__main__":
    unittest.main()

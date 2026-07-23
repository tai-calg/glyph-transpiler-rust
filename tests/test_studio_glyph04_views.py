from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from glyph.studio import GlyphStudio
from glyph.studio_views import build_studio_views


ROOT = Path(__file__).resolve().parents[1]


class Glyph04StudioViewTests(unittest.TestCase):
    def test_plain_design_keeps_glyph04_views_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "plain.glyph"
            source.write_text(">inc(x:U):U=x+1\n", encoding="utf-8")

            snapshot = GlyphStudio(source).rebuild()

            self.assertFalse(snapshot.glyph04_views["enabled"])
            self.assertEqual(snapshot.glyph04_views["summary"]["resources"], 0)
            self.assertIn("studio-views.json", snapshot.artifacts)
            self.assertNotIn("manual.rs", snapshot.artifacts)

    def test_complete_system_projects_all_seven_orthogonal_views(self) -> None:
        source_text = (
            ROOT / "examples" / "acceptance" / "glyph04_system.glyph"
        ).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "glyph04_system.glyph"
            source.write_text(source_text, encoding="utf-8")

            studio = GlyphStudio(source)
            snapshot = studio.rebuild()
            view_model = snapshot.glyph04_views
            views = view_model["views"]

            self.assertEqual(view_model["schema"], "glyph.studio-views")
            self.assertTrue(view_model["enabled"])
            self.assertEqual(
                set(views),
                {
                    "capability",
                    "resource",
                    "world_region",
                    "protocol",
                    "handler",
                    "law",
                    "verification_strength",
                },
            )
            self.assertEqual(view_model["summary"]["resources"], 1)
            self.assertEqual(view_model["summary"]["worlds"], 3)
            self.assertEqual(view_model["summary"]["protocols"], 1)
            self.assertEqual(view_model["summary"]["handlers"], 2)
            self.assertEqual(view_model["summary"]["laws"], 1)

            identities = views["resource"]["identities"]
            self.assertEqual(len(identities), 1)
            self.assertEqual(identities[0]["resource"], "Buffer")
            self.assertEqual(set(identities[0]["states"]), {"Ready", "Done"})

            protocol = views["protocol"]["protocols"][0]
            self.assertEqual(
                [event["direction"] for event in protocol["events"]],
                ["send", "receive"],
            )
            self.assertEqual(
                [event["type"] for event in protocol["events"]],
                ["Input", "Output"],
            )

            handlers = {item["name"]: item for item in views["handler"]["handlers"]}
            self.assertIn("Deadline", handlers)
            self.assertIn("RetryPolicy", handlers)
            self.assertEqual(handlers["Deadline"]["edges"][0]["source"], "target")

            law = views["law"]["laws"][0]
            self.assertEqual(law["name"], "ObservationSafe")
            self.assertTrue(law["applications"])

            verification = views["verification_strength"]
            self.assertEqual(
                [item["name"] for item in verification["classes"]],
                ["static", "model", "runtime", "trusted"],
            )
            self.assertTrue(verification["matrix"])

            serialized = json.loads(snapshot.artifacts["studio-views.json"])
            self.assertEqual(serialized, view_model)
            self.assertEqual(studio.state_dict()["glyph04_views"], view_model)

    def test_projection_uses_typed_design_without_source_parsing(self) -> None:
        design = {
            "runtime_contracts": {
                "worlds": [
                    {
                        "name": "Worker",
                        "locus": "Worker",
                        "region": ["App", "Task"],
                        "line": 1,
                    }
                ],
                "protocols": [],
                "handlers": [],
                "laws": [],
                "applications": [],
            },
            "verification": {"summary": {}, "items": []},
        }

        projected = build_studio_views(design)

        self.assertTrue(projected["enabled"])
        self.assertEqual(
            projected["views"]["world_region"]["worlds"][0]["region_path"],
            "App/Task",
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from glyph.compilation import compile_outputs
from glyph.studio import GlyphStudio
from glyph.studio_views import build_studio_views


ROOT = Path(__file__).resolve().parents[1]


class GlyphStudioSemanticNavigationTests(unittest.TestCase):
    def test_complete_system_has_closed_semantic_graph(self) -> None:
        source_text = (
            ROOT / "examples" / "acceptance" / "glyph04_system.glyph"
        ).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "glyph04_system.glyph"
            source.write_text(source_text, encoding="utf-8")

            snapshot = GlyphStudio(source).rebuild()
            model = snapshot.glyph04_views
            index = model["semantic_index"]

        self.assertEqual(model["schema"], "glyph.studio-views")
        self.assertEqual(model["version"], 2)
        self.assertEqual(index["schema"], "glyph.studio-semantic-index")
        self.assertEqual(index["version"], 1)

        entities = index["entities"]
        relations = index["relations"]
        entity_ids = [item["id"] for item in entities]
        self.assertEqual(len(entity_ids), len(set(entity_ids)))
        entity_id_set = set(entity_ids)
        for relation in relations:
            self.assertIn(relation["source"], entity_id_set)
            self.assertIn(relation["target"], entity_id_set)
            self.assertIn(relation["kind"], index["relation_kinds"])

        for entity_id in (
            "function:process",
            "resource:Buffer",
            "identity:rho:process:buffer",
            "world:WorkerRequest",
            "protocol:NormalizeExchange",
            "handler:RetryPolicy",
            "law:ObservationSafe",
        ):
            self.assertIn(entity_id, entity_id_set)

        for invalid_id in (
            "effect:process",
            "resource:0",
            "resource:1",
            "type:0",
            "type:1",
        ):
            self.assertNotIn(invalid_id, entity_id_set)

        relation_triples = {
            (item["source"], item["kind"], item["target"])
            for item in relations
        }
        self.assertIn(
            (
                "function:process",
                "transitions",
                "identity:rho:process:buffer",
            ),
            relation_triples,
        )
        self.assertIn(
            ("function:process", "executes-in", "world:WorkerRequest"),
            relation_triples,
        )
        self.assertIn(
            ("function:normalize", "uses-protocol", "protocol:NormalizeExchange"),
            relation_triples,
        )
        self.assertIn(
            ("function:fetch", "handled-by", "handler:RetryPolicy"),
            relation_triples,
        )
        self.assertIn(
            ("aggregate:ProcessError", "stores", "resource:Buffer"),
            relation_triples,
        )
        self.assertIn(
            ("aggregate:ProcessError", "stores", "type:E"),
            relation_triples,
        )

    def test_projection_is_deterministic_and_does_not_change_public_ir(self) -> None:
        source = (
            ROOT / "examples" / "acceptance" / "glyph04_system.glyph"
        ).read_text(encoding="utf-8")
        outputs = compile_outputs(source, "glyph04_system.glyph")
        design = json.loads(outputs.design_json)
        before = json.loads(outputs.design_json)

        first = build_studio_views(design)
        second = build_studio_views(design)

        self.assertEqual(first, second)
        self.assertEqual(design, before)
        self.assertNotIn("semantic_index", design)
        self.assertNotIn("studio_views", design)

    def test_plain_design_has_an_empty_semantic_index(self) -> None:
        projected = build_studio_views(
            {
                "verification": {"summary": {}, "items": []},
                "runtime_contracts": {
                    "worlds": [],
                    "protocols": [],
                    "handlers": [],
                    "laws": [],
                    "applications": [],
                },
            }
        )

        self.assertFalse(projected["enabled"])
        self.assertEqual(projected["semantic_index"]["entities"], [])
        self.assertEqual(projected["semantic_index"]["relations"], [])

    def test_effect_application_uses_the_function_entity(self) -> None:
        design = {
            "runtime_contracts": {
                "worlds": [
                    {
                        "name": "WorkerTask",
                        "locus": "Worker",
                        "region": ["App", "Task"],
                        "line": 1,
                    }
                ],
                "protocols": [],
                "handlers": [],
                "laws": [],
                "applications": [
                    {
                        "target": "process",
                        "target_kind": "effect",
                        "row": {
                            "world": "WorkerTask",
                            "protocol": None,
                            "handler": None,
                            "laws": [],
                        },
                        "line": 4,
                    }
                ],
            },
            "verification": {"summary": {}, "items": []},
        }

        projected = build_studio_views(design)
        entities = {
            item["id"]: item for item in projected["semantic_index"]["entities"]
        }
        relations = {
            (item["source"], item["kind"], item["target"])
            for item in projected["semantic_index"]["relations"]
        }

        self.assertIn("function:process", entities)
        self.assertNotIn("effect:process", entities)
        self.assertIn(
            ("function:process", "executes-in", "world:WorkerTask"),
            relations,
        )

    def test_protocol_paths_are_stable_without_false_linear_relations(self) -> None:
        design = {
            "runtime_contracts": {
                "worlds": [],
                "protocols": [
                    {
                        "name": "Structured",
                        "line": 3,
                        "root": {
                            "kind": "choice",
                            "type": None,
                            "children": [
                                {
                                    "kind": "sequence",
                                    "type": None,
                                    "children": [
                                        {"kind": "send", "type": "A", "children": []},
                                        {"kind": "receive", "type": "B", "children": []},
                                    ],
                                },
                                {
                                    "kind": "parallel",
                                    "type": None,
                                    "children": [
                                        {"kind": "send", "type": "C", "children": []},
                                        {"kind": "receive", "type": "D", "children": []},
                                    ],
                                },
                            ],
                        },
                    }
                ],
                "handlers": [],
                "laws": [],
                "applications": [],
            },
            "verification": {"summary": {}, "items": []},
        }

        projected = build_studio_views(design)
        events = projected["views"]["protocol"]["protocols"][0]["events"]
        self.assertEqual(
            [item["entity_id"] for item in events],
            [
                "protocol-event:Structured:root.0.0",
                "protocol-event:Structured:root.0.1",
                "protocol-event:Structured:root.1.0",
                "protocol-event:Structured:root.1.1",
            ],
        )
        event_ids = {item["entity_id"] for item in events}
        false_linear_edges = [
            item
            for item in projected["semantic_index"]["relations"]
            if item["kind"] == "next"
            and item["source"] in event_ids
            and item["target"] in event_ids
        ]
        self.assertEqual(false_linear_edges, [])

    def test_unknown_verification_subject_is_retained(self) -> None:
        design = {
            "runtime_contracts": {
                "worlds": [],
                "protocols": [],
                "handlers": [],
                "laws": [],
                "applications": [],
            },
            "verification": {
                "summary": {"trusted": 1},
                "items": [
                    {
                        "subject": "external clock",
                        "axis": "runtime",
                        "classes": ["trusted"],
                        "statement": "Host supplies monotonic time",
                        "line": None,
                    }
                ],
            },
        }

        projected = build_studio_views(design)
        entities = projected["semantic_index"]["entities"]
        relations = projected["semantic_index"]["relations"]
        subject = next(item for item in entities if item["kind"] == "subject")
        verification = next(
            item for item in entities if item["kind"] == "verification"
        )
        self.assertIn(
            {
                "source": subject["id"],
                "kind": "verified-by",
                "target": verification["id"],
                "line": None,
                "views": ["Verification"],
                "details": {},
            },
            relations,
        )


if __name__ == "__main__":
    unittest.main()

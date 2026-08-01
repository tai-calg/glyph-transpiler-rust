from __future__ import annotations

import unittest

from glyph.transition_analysis.semantic_event import (
    action_event_reference_ids,
    actions_are_same_semantic_events,
    attach_context_semantic_event_refs,
    attach_machine_action_aliases,
)


class SemanticEventIdentityTests(unittest.TestCase):
    def test_repeated_equal_effects_keep_distinct_dynamic_event_ids(self) -> None:
        context = {
            "system": "Audit",
            "entry": "run",
            "effect_trace": {
                "alternatives": [
                    {
                        "condition": None,
                        "events": [
                            {"operation": "log", "expression": "log(x)"},
                            {"operation": "log", "expression": "log(x)"},
                        ],
                    }
                ]
            },
        }
        attach_context_semantic_event_refs(
            context,
            program_fingerprint="program",
            edge_fingerprint="edge",
        )
        events = context["effect_trace"]["alternatives"][0]["events"]
        first = events[0]["semantic_event_ref"]
        second = events[1]["semantic_event_ref"]

        self.assertEqual(first["static_event_id"], second["static_event_id"])
        self.assertEqual(first["trace_position"], 0)
        self.assertEqual(second["trace_position"], 1)
        self.assertNotEqual(first["id"], second["id"])

    def test_complete_matching_machine_sequence_is_marked_as_alias(self) -> None:
        system_action = {
            "kind": "effect-trace",
            "events": [
                {
                    "operation": "log",
                    "expression": "log(x)",
                    "failure_type": None,
                    "semantic_event_ref": {"id": "event-0"},
                },
                {
                    "operation": "log",
                    "expression": "log(x)",
                    "failure_type": None,
                    "semantic_event_ref": {"id": "event-1"},
                },
            ],
        }
        transition = {
            "machine_action": {"display": "log(x); log(x)"},
            "machine_action_invocations": [
                {"operation": "log", "expression": "log(x)", "failure_type": None},
                {"operation": "log", "expression": "log(x)", "failure_type": None},
            ],
            "machine_effect_invocations": [
                {"operation": "log", "expression": "log(x)", "failure_type": None},
                {"operation": "log", "expression": "log(x)", "failure_type": None},
            ],
        }
        result = attach_machine_action_aliases(transition, system_action)

        self.assertEqual(
            action_event_reference_ids(result["machine_action"]),
            ("event-0", "event-1"),
        )
        self.assertEqual(
            action_event_reference_ids(system_action),
            ("event-0", "event-1"),
        )
        self.assertTrue(
            actions_are_same_semantic_events(result["machine_action"], system_action)
        )
        self.assertEqual(
            [item["alias_of_event_id"] for item in result["machine_action_invocations"]],
            ["event-0", "event-1"],
        )
        self.assertEqual(result["semantic_action_aliasing"]["event_count"], 2)

    def test_equal_text_without_event_identity_is_not_deduplicated(self) -> None:
        machine = {"display": "log(x)"}
        system = {
            "kind": "effect-trace",
            "events": [{"operation": "log", "expression": "log(x)"}],
        }
        self.assertFalse(actions_are_same_semantic_events(machine, system))

    def test_different_multiplicity_is_not_marked_as_alias(self) -> None:
        transition = {
            "machine_action": {"display": "log(x); log(x)"},
            "machine_action_invocations": [
                {"operation": "log", "expression": "log(x)"},
                {"operation": "log", "expression": "log(x)"},
            ],
        }
        system_action = {
            "kind": "effect-trace",
            "events": [
                {
                    "operation": "log",
                    "expression": "log(x)",
                    "semantic_event_ref": {"id": "event-0"},
                }
            ],
        }
        result = attach_machine_action_aliases(transition, system_action)
        self.assertNotIn("semantic_action_aliasing", result)
        self.assertNotIn("semantic_event_refs", result["machine_action"])

    def test_different_order_is_not_marked_as_alias(self) -> None:
        transition = {
            "machine_action": {"display": "open(); log()"},
            "machine_action_invocations": [
                {"operation": "open", "expression": "open()"},
                {"operation": "log", "expression": "log()"},
            ],
        }
        system_action = {
            "kind": "effect-trace",
            "events": [
                {
                    "operation": "log",
                    "expression": "log()",
                    "semantic_event_ref": {"id": "event-0"},
                },
                {
                    "operation": "open",
                    "expression": "open()",
                    "semantic_event_ref": {"id": "event-1"},
                },
            ],
        }
        result = attach_machine_action_aliases(transition, system_action)
        self.assertNotIn("semantic_action_aliasing", result)


if __name__ == "__main__":
    unittest.main()

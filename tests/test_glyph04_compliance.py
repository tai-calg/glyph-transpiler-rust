from __future__ import annotations

import json
from pathlib import Path
import unittest

from glyph import compile_outputs
from glyph.compliance import REQUIREMENTS, build_compliance_report
from glyph.schema import GLYPH04_PUBLIC_SCHEMAS


ROOT = Path(__file__).resolve().parents[1]


class Glyph04ComplianceTests(unittest.TestCase):
    def test_requirement_evidence_resolves(self) -> None:
        report = build_compliance_report(ROOT)

        self.assertTrue(report.passed, "\n".join(report.errors))
        self.assertGreaterEqual(len(report.requirements), 18)

    def test_every_static_rule_has_negative_evidence(self) -> None:
        missing = [
            requirement.id
            for requirement in REQUIREMENTS
            if requirement.static_rule and not requirement.negative_tests
        ]

        self.assertEqual(missing, [])

    def test_glyph04_public_schema_envelopes_and_shapes_are_frozen(self) -> None:
        source = (ROOT / "examples" / "acceptance" / "glyph04_system.glyph").read_text(
            encoding="utf-8"
        )
        outputs = compile_outputs(source, "glyph04_system.glyph")
        expected_keys = {
            "capability-ir.json": {
                "schema",
                "version",
                "resources",
                "functions",
                "aggregates",
                "operations",
            },
            "resource-flow-ir.json": {"schema", "version", "transitions"},
            "contracts-ir.json": {
                "schema",
                "version",
                "declarations",
                "applications",
            },
            "runtime-contract-ir.json": {
                "schema",
                "version",
                "worlds",
                "protocols",
                "handlers",
                "laws",
                "rows",
                "applications",
            },
            "verification-report.json": {"schema", "version", "summary", "items"},
            "host-requirements-ir.json": {
                "schema",
                "version",
                "representations",
                "operations",
                "invariants",
            },
        }

        for filename, (schema, version) in GLYPH04_PUBLIC_SCHEMAS.items():
            with self.subTest(filename=filename):
                payload = json.loads(outputs.diagrams.files[filename])
                self.assertEqual(payload["schema"], schema)
                self.assertEqual(payload["version"], version)
                self.assertEqual(set(payload), expected_keys[filename])

    def test_symbolic_identity_shape_is_frozen(self) -> None:
        source = (
            "resource Buffer[Ready|Used]\n"
            "+E=Bad\n"
            "*WriteError(buffer:own Buffer[Ready],cause:E)\n"
            "!write(buffer:own Buffer[Ready]):own Buffer[Used]|WriteError\n"
        )
        outputs = compile_outputs(source)
        payload = json.loads(outputs.diagrams.files["resource-flow-ir.json"])
        transitions = payload["transitions"]

        self.assertGreaterEqual(len(transitions), 2)
        self.assertEqual(
            {item["target"]["identity"] for item in transitions},
            {"rho:write:buffer"},
        )
        self.assertEqual(
            set(transitions[0]),
            {"function", "identity", "source", "target", "kind", "line"},
        )
        self.assertEqual(
            set(transitions[0]["target"]),
            {"place", "resource", "state", "capability", "identity"},
        )


if __name__ == "__main__":
    unittest.main()

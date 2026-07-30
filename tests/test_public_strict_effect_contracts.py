from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

from glyph.compilation import CompilationPipeline
from glyph.compiler import ExternDecl
from glyph.transition_analysis import (
    BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID,
    PUBLIC_STRICT_EXCLUSIONS,
    PUBLIC_STRICT_PROGRAMS,
    VerifiedEffectContractRegistry,
    audit_effect_contract_coverage,
    public_strict_surface_ir,
)
from glyph.transition_analysis.abstract_value import TopValue


ROOT = Path(__file__).resolve().parents[1]


def _builtin_default_source() -> str:
    tree = ast.parse((ROOT / "glyph.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "DEFAULT_SOURCE"
            for target in node.targets
        ):
            continue
        value = ast.literal_eval(node.value)
        if isinstance(value, str):
            return value
    raise AssertionError("glyph.py DEFAULT_SOURCE is unavailable")


def _program_source(source_id: str, source_path: str | None) -> str:
    if source_id == BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID:
        return _builtin_default_source()
    if source_path is None:
        raise AssertionError(f"public strict source path missing for {source_id}")
    return (ROOT / source_path).read_text(encoding="utf-8")


class PublicStrictEffectContractTests(unittest.TestCase):
    def test_included_surface_matches_compiled_effects_and_replay_contracts(self) -> None:
        self.assertGreater(len(PUBLIC_STRICT_PROGRAMS), 1)
        for program in PUBLIC_STRICT_PROGRAMS:
            with self.subTest(source=program.source_id):
                compiled = CompilationPipeline().compile_text(
                    _program_source(program.source_id, program.source_path),
                    source_name=program.source_id,
                )
                report = audit_effect_contract_coverage(
                    compiled.model,
                    (program.entry,),
                    program.registry(),
                )
                self.assertTrue(report.complete, report.to_ir())
                self.assertEqual(len(report.entries), 1)
                entry = report.entries[0]
                self.assertEqual(
                    set(entry.required_operations),
                    set(program.operations),
                )
                self.assertEqual(entry.missing_operations, ())

                declarations = {
                    declaration.name: declaration
                    for declaration in compiled.model.program.declarations
                    if isinstance(declaration, ExternDecl)
                }
                for case in program.cases:
                    contract = case.contract
                    declaration = declarations.get(contract.operation)
                    self.assertIsNotNone(declaration)
                    assert declaration is not None
                    self.assertEqual(
                        contract.summary.parameters,
                        tuple(item.name for item in declaration.params),
                    )
                    self.assertEqual(
                        contract.handler(case.replay_arguments),
                        case.expected_result,
                    )
                    self.assertEqual(contract.failure_values, ())
                    self.assertEqual(contract.summary.completions, ("normal",))
                    self.assertFalse(contract.summary.unknown_write_footprint)
                    self.assertNotIsInstance(contract.summary.return_value, TopValue)

                    external_locations = tuple(
                        sorted(
                            location.key
                            for write in contract.summary.writes
                            for location in write.address.locations
                            if location.kind == "external"
                        )
                    )
                    self.assertEqual(
                        external_locations,
                        tuple(sorted(case.expected_external_locations)),
                    )
                    self.assertTrue(
                        all(
                            write.address.singleton_proven
                            for write in contract.summary.writes
                        )
                    )

                    payload = contract.to_ir()
                    self.assertEqual(payload["failure_values"], [])
                    self.assertEqual(payload["unknown_write_footprint"], False)
                    self.assertIn("return_value", payload)
                    self.assertEqual(
                        len(payload["writes"]),
                        len(case.expected_external_locations),
                    )

    def test_failure_capable_examples_remain_explicitly_excluded(self) -> None:
        empty = VerifiedEffectContractRegistry()
        checked = 0
        for exclusion in PUBLIC_STRICT_EXCLUSIONS:
            if exclusion.entry is None:
                self.assertIn("no System entry", exclusion.reason)
                continue
            with self.subTest(source=exclusion.source_path):
                source = (ROOT / exclusion.source_path).read_text(encoding="utf-8")
                compiled = CompilationPipeline().compile_text(
                    source,
                    source_name=exclusion.source_path,
                )
                report = audit_effect_contract_coverage(
                    compiled.model,
                    (exclusion.entry,),
                    empty,
                )
                self.assertFalse(report.complete)
                self.assertEqual(
                    set(report.missing_operations),
                    set(exclusion.operations),
                )
                self.assertTrue(exclusion.reason.strip())
                checked += 1
        self.assertGreater(checked, 0)

    def test_surface_manifest_is_stable_and_json_serializable(self) -> None:
        payload = public_strict_surface_ir()
        self.assertEqual(payload["version"], 1)
        source_ids = [item["source_id"] for item in payload["included"]]
        self.assertEqual(len(source_ids), len(set(source_ids)))
        self.assertGreater(len(payload["excluded"]), 0)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertIn("write_motor", encoded)
        self.assertIn("submit_batch", encoded)
        self.assertIn("failure_values", encoded)
        self.assertIn("external", encoded)


if __name__ == "__main__":
    unittest.main()

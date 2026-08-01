from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from glyph.compilation import CompilationPipeline
from glyph.transition_analysis.effect_contract import (
    VerifiedEffectContractRegistry,
    read_only_identity_contract,
)
from glyph.transition_analysis.projection import check_exact_action_projection
from glyph.transition_analysis.witness_binding import (
    bind_witness_generation_report,
    relation_edge_fingerprints,
    runtime_program_fingerprint,
    typed_concrete_value_ir,
)
from glyph.transition_analysis.witness_generation import (
    generate_bounded_system_witnesses,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/acceptance/rtai_strict_projection.glyph"


def _exact(scope: str) -> dict[str, object]:
    return {
        "kind": "exact",
        "causes": [],
        "proofs": [
            {
                "kind": "structural-identity",
                "scope": scope,
                "detail": f"test {scope}",
            }
        ],
    }


def _native_context() -> dict[str, object]:
    program = "program-fingerprint"
    edge = "edge-fingerprint"
    return {
        "edge_id": "T1",
        "system": "DoorControl",
        "entry": "control",
        "scope": "system",
        "evidence_origin": "rtai-native",
        "program_fingerprint": program,
        "analysis_edge_fingerprint": edge,
        "reachability": {
            "status": "proven-reachable",
            "precondition": "True",
            "witness": {
                "edge_id": "T1",
                "analysis_edge_id": "Door:step:1:0",
                "completion": "returned",
                "binding": {
                    "version": 1,
                    "program_fingerprint": program,
                    "edge_fingerprint": edge,
                    "contract_digest": "contract-digest",
                    "interpreter_version": "teir-concrete-v1",
                    "input_digest": "input-digest",
                },
            },
            "approximation": _exact("reachability"),
        },
        "cardinality": {
            "upper_bound": "at-most-one",
            "witness": None,
            "approximation": _exact("cardinality"),
        },
        "effect_trace": {
            "is_singleton": True,
            "alternatives": [
                {
                    "condition": None,
                    "events": [
                        {"operation": "actuator", "expression": "actuator(state)"}
                    ],
                }
            ],
            "approximation": _exact("effect-trace"),
        },
        "completion": {
            "kinds": ["normal"],
            "approximation": _exact("completion"),
        },
        "unknown_reasons": [],
    }


class WitnessBindingTests(unittest.TestCase):
    def test_valid_native_binding_authorizes_exact_projection(self) -> None:
        decision = check_exact_action_projection(_native_context())
        self.assertTrue(decision.allowed, decision.to_ir())
        self.assertEqual(decision.action["kind"], "effect-trace")

    def test_missing_native_binding_is_rejected(self) -> None:
        context = _native_context()
        del context["reachability"]["witness"]["binding"]
        decision = check_exact_action_projection(context)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "concrete-witness-binding-is-missing")

    def test_cross_program_witness_is_rejected(self) -> None:
        context = _native_context()
        context["reachability"]["witness"]["binding"][
            "program_fingerprint"
        ] = "different-program"
        decision = check_exact_action_projection(context)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "concrete-witness-program-mismatch")

    def test_cross_edge_witness_is_rejected(self) -> None:
        context = _native_context()
        context["reachability"]["witness"]["binding"][
            "edge_fingerprint"
        ] = "different-edge"
        decision = check_exact_action_projection(context)
        self.assertFalse(decision.allowed)
        self.assertEqual(
            decision.reason,
            "concrete-witness-edge-fingerprint-mismatch",
        )

    def test_incomplete_binding_is_rejected(self) -> None:
        context = _native_context()
        context["reachability"]["witness"]["binding"]["contract_digest"] = ""
        decision = check_exact_action_projection(context)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "concrete-witness-binding-is-incomplete")

    def test_legacy_context_remains_migration_compatible(self) -> None:
        context = _native_context()
        context.pop("evidence_origin")
        context.pop("program_fingerprint")
        context.pop("analysis_edge_fingerprint")
        context["reachability"]["witness"].pop("binding")
        decision = check_exact_action_projection(context)
        self.assertTrue(decision.allowed, decision.to_ir())

    def test_typed_value_digest_distinguishes_integer_and_float(self) -> None:
        self.assertNotEqual(
            typed_concrete_value_ir(1),
            typed_concrete_value_ir(1.0),
        )
        self.assertEqual(
            typed_concrete_value_ir(1.0),
            {"kind": "float", "value": "0x1.0000000000000p+0"},
        )

    def test_duplicate_relation_edge_ids_receive_no_authorizing_fingerprint(self) -> None:
        edges = (
            SimpleNamespace(
                edge_id="duplicate-edge",
                ordinal=0,
                effective_guard="left",
                result_expression="A",
                target_state="A",
                completion="normal",
            ),
            SimpleNamespace(
                edge_id="duplicate-edge",
                ordinal=1,
                effective_guard="right",
                result_expression="B",
                target_state="B",
                completion="normal",
            ),
        )
        relation = SimpleNamespace(
            machine_id="Machine",
            transition_function="step",
            formals=("state", "input"),
            edges=edges,
        )
        model = SimpleNamespace(machines=(SimpleNamespace(name="Machine"),))

        with patch(
            "glyph.transition_analysis.witness_binding.build_machine_relation",
            return_value=relation,
        ):
            fingerprints = relation_edge_fingerprints(model)

        self.assertNotIn("duplicate-edge", fingerprints)
        self.assertEqual(fingerprints, {})

    def test_generated_witnesses_are_bound_to_current_program_and_edges(self) -> None:
        source = FIXTURE.read_text(encoding="utf-8")
        compiled = CompilationPipeline().compile_text(source, source_name=str(FIXTURE))
        contract = read_only_identity_contract(
            "actuator",
            "state",
            source="test reviewed identity",
        )
        contracts = VerifiedEffectContractRegistry(
            by_entry=(("control", (("actuator", contract),)),)
        )
        base = generate_bounded_system_witnesses(
            compiled.model,
            ("control",),
            contracts,
        )
        bound = bind_witness_generation_report(base, compiled.model, contracts)

        self.assertTrue(bound.complete, bound.to_ir())
        self.assertEqual(
            bound.program_fingerprint,
            runtime_program_fingerprint(compiled.model),
        )
        edge_fingerprints = relation_edge_fingerprints(compiled.model)
        self.assertTrue(bound.witnesses)
        for item in bound.witnesses:
            binding = item.witness.binding
            self.assertEqual(binding.program_fingerprint, bound.program_fingerprint)
            self.assertEqual(binding.edge_fingerprint, edge_fingerprints[item.edge_id])
            self.assertTrue(binding.contract_digest)
            self.assertTrue(binding.input_digest)
            self.assertEqual(binding.interpreter_version, "teir-concrete-v1")

    def test_source_edit_changes_runtime_program_fingerprint(self) -> None:
        source = FIXTURE.read_text(encoding="utf-8")
        original = CompilationPipeline().compile_text(source, source_name=str(FIXTURE))
        edited = CompilationPipeline().compile_text(
            source + "\n# unreviewed\n",
            source_name=str(FIXTURE),
        )
        self.assertNotEqual(
            runtime_program_fingerprint(original.model),
            runtime_program_fingerprint(edited.model),
        )


if __name__ == "__main__":
    unittest.main()

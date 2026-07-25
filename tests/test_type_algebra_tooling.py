from __future__ import annotations

import json
import unittest

from glyph import compile_outputs, parse_compilation_model
from glyph.execution_ir import build_execution_structure_ir
from glyph.type_algebra import (
    build_machine_coverage,
    build_type_algebra_ir,
    tooling_payload,
)


def _coverage(source: str):
    model = parse_compilation_model(source, "machine.glyph")
    execution = build_execution_structure_ir(
        model.preprocess.source,
        "machine.glyph",
        model.expanded.program,
        model.expanded.specs,
        model.expanded.machines,
    )
    algebra = build_type_algebra_ir("machine.glyph", model.expanded.program)
    coverage = build_machine_coverage(
        model.expanded.program,
        model.expanded.machines,
        execution,
        algebra,
    )
    return algebra, coverage


class TypeAlgebraToolingTests(unittest.TestCase):
    def test_impossible_type_and_unreachable_function_diagnostics_are_emitted(self) -> None:
        outputs = compile_outputs(
            "resource Token[Ready]\n"
            "*Impossible(value:Never)\n"
            ">consume(value:Impossible):bool=true\n",
            "diagnostics.glyph",
        )
        payload = json.loads(outputs.diagrams.files["type-algebra-ir.json"])
        diagnostics = {item["code"] for item in payload["diagnostics"]}
        self.assertIn("type-algebra-impossible", diagnostics)
        self.assertIn("type-algebra-unreachable-function", diagnostics)

    def test_structural_distribution_and_factoring_generate_rust(self) -> None:
        outputs = compile_outputs(
            "resource Token[Ready]\n"
            "+Choice=Alpha{alpha:bool}|Beta{beta:bool}\n"
            "*Left(context:bool,choice:Choice)\n"
            "*ContextAlpha(context:bool,alpha:bool)\n"
            "*ContextBeta(context:bool,beta:bool)\n"
            "+Right=InAlpha(ContextAlpha)|InBeta(ContextBeta)\n",
            "distribution.glyph",
        )
        payload = json.loads(outputs.diagrams.files["type-algebra-ir.json"])
        structural = next(
            item
            for item in payload["structural_conversions"]
            if item["source_type"] == "Left" and item["target_type"] == "Right"
        )
        self.assertTrue(structural["generated"])
        self.assertEqual(
            [step["law"] for step in structural["steps"]],
            ["distribute", "factor"],
        )
        generated = outputs.diagrams.files["type-algebra.generated.rs"]
        self.assertIn("glyph_distribute_left_to_right", generated)
        self.assertIn("glyph_factor_right_to_left", generated)
        self.assertIn("Choice::Alpha", generated)
        self.assertIn("Right::InAlpha", generated)

    def test_machine_coverage_uses_selector_not_entire_state_product(self) -> None:
        source = (
            "resource Token[Ready]\n"
            "+Mode=Idle|Running\n"
            "+Event=Start|Stop\n"
            "*State(mode:Mode,count:u64)\n"
            ">next(state:State,event:Event):State=state\n"
            "machine Controller(state:State,event:Event)\n"
            "  select=state.mode\n"
            "  init=State(Idle,0)\n"
            "  next=next(state,event)\n"
            "  success=Running\n"
            "  failure=Idle\n"
        )
        _, coverage = _coverage(source)
        self.assertEqual(len(coverage), 1)
        result = coverage[0]
        self.assertEqual(result.domain_semantics, "selector×input")
        self.assertEqual(result.selector_field, "mode")
        self.assertEqual(result.selector_type, "Mode")
        self.assertEqual(result.state_cardinality, "2")
        self.assertEqual(result.selector_cardinality, "2")
        self.assertEqual(result.input_cardinality, "2")
        self.assertEqual(result.possible_pairs, "4")
        self.assertEqual(result.defined_pairs, 4)
        self.assertEqual(result.missing_pairs, "0")
        self.assertTrue(result.complete)
        self.assertTrue(result.exact)

    def test_machine_coverage_detects_missing_overlap_and_shadowed_guard(self) -> None:
        source = (
            "resource Token[Ready]\n"
            "+Mode=Idle|Running|Stopped\n"
            "+Event=Start|Stop\n"
            "*State(mode:Mode)\n"
            ">next(state:State,event:Event):State\n"
            "  state.mode==Idle >> State(Running)\n"
            "  state.mode==Idle >> State(Idle)\n"
            "  state.mode==Running >> State(Idle)\n"
            "  _ >> state\n"
            "machine Controller(state:State,event:Event)\n"
            "  select=state.mode\n"
            "  init=State(Idle)\n"
            "  next=next(state,event)\n"
            "  success=Running\n"
            "  failure=Stopped\n"
        )
        algebra, coverage = _coverage(source)
        result = coverage[0]
        self.assertEqual(result.possible_pairs, "6")
        self.assertEqual(result.defined_pairs, 4)
        self.assertEqual(result.fallthrough_pairs, 2)
        self.assertEqual(result.missing_pairs, "0")
        self.assertEqual(result.overlap_pairs, 2)
        self.assertTrue(result.complete)
        self.assertEqual(result.guards[1].classification, "shadowed")
        self.assertTrue(result.guards[1].unreachable)
        payload = tooling_payload(
            algebra.diagnostics,
            algebra.structural_conversions,
            coverage,
        )
        codes = {item["code"] for item in payload["diagnostics"]}
        self.assertIn("machine-coverage-overlap", codes)
        self.assertIn("machine-coverage-unreachable", codes)

    def test_machine_coverage_classifies_rejection_and_default_fallthrough(self) -> None:
        source = (
            "resource Token[Ready]\n"
            "+Mode=Idle|Running\n"
            "+Event=Start|Stop\n"
            "+Error=Bad\n"
            "*State(mode:Mode)\n"
            ">next(state:State,event:Event):State|Error\n"
            "  state.mode==Idle >> Err(Bad)\n"
            "  _ >> Ok(state)\n"
            "machine Controller(state:State,event:Event)\n"
            "  select=state.mode\n"
            "  init=State(Idle)\n"
            "  next=next(state,event)\n"
            "  success=Running\n"
            "  failure=Idle\n"
        )
        _, coverage = _coverage(source)
        result = coverage[0]
        self.assertEqual(result.rejected_pairs, 2)
        self.assertEqual(result.fallthrough_pairs, 2)
        self.assertEqual(result.missing_pairs, "0")
        self.assertEqual(result.unknown_pairs, 0)
        self.assertTrue(result.complete)

    def test_unknown_state_predicate_is_not_reported_as_missing(self) -> None:
        source = (
            "resource Token[Ready]\n"
            "+Mode=Idle|Running\n"
            "+Event=Start|Stop\n"
            "*State(mode:Mode,count:u64)\n"
            ">next(state:State,event:Event):State\n"
            "  state.count>0 >> State(Running,0)\n"
            "  _ >> state\n"
            "machine Controller(state:State,event:Event)\n"
            "  select=state.mode\n"
            "  init=State(Idle,0)\n"
            "  next=next(state,event)\n"
            "  success=Running\n"
            "  failure=Idle\n"
        )
        algebra, coverage = _coverage(source)
        result = coverage[0]
        self.assertEqual(result.missing_pairs, "0")
        self.assertEqual(result.unknown_pairs, 4)
        self.assertFalse(result.complete)
        payload = tooling_payload(
            algebra.diagnostics,
            algebra.structural_conversions,
            coverage,
        )
        codes = {item["code"] for item in payload["diagnostics"]}
        self.assertIn("machine-coverage-unknown", codes)
        self.assertNotIn("machine-coverage-missing", codes)

    def test_u8_input_is_partitioned_by_guard_boundaries(self) -> None:
        source = (
            "resource Token[Ready]\n"
            "+Mode=Idle|Running\n"
            "+Error=Rejected\n"
            "*State(mode:Mode)\n"
            ">next(state:State,value:u8):State|Error\n"
            "  value<10 >> Err(Rejected)\n"
            "  value==100 >> Ok(State(Running))\n"
            "  _ >> Ok(state)\n"
            "machine Controller(state:State,value:u8)\n"
            "  select=state.mode\n"
            "  init=State(Idle)\n"
            "  next=next(state,value)\n"
            "  success=Running\n"
            "  failure=Idle\n"
        )
        _, coverage = _coverage(source)
        result = coverage[0]
        self.assertTrue(result.partitioned)
        self.assertEqual(
            result.domain_semantics,
            "selector×symbolic-input-partition",
        )
        self.assertEqual(result.input_cardinality, "256")
        self.assertEqual(result.possible_pairs, "512")
        self.assertEqual(result.region_count, 8)
        self.assertEqual(result.rejected_pairs, 20)
        self.assertEqual(result.defined_pairs, 2)
        self.assertEqual(result.fallthrough_pairs, 490)
        self.assertEqual(result.missing_pairs, "0")
        self.assertEqual(result.unknown_pairs, 0)
        self.assertTrue(result.complete)
        self.assertTrue(result.exact)
        regions = {
            binding.value
            for case in result.cases
            for binding in case.regions
            if binding.name == "value"
        }
        self.assertEqual(
            regions,
            {"0..=9", "10..=99", "100", "101..=255"},
        )
        self.assertEqual(
            sum(int(case.multiplicity) for case in result.cases),
            512,
        )

    def test_u64_domain_keeps_exact_concrete_counts_without_enumeration(self) -> None:
        source = (
            "resource Token[Ready]\n"
            "+Mode=Idle|Running\n"
            "*State(mode:Mode)\n"
            ">next(state:State,value:u64):State\n"
            "  value==0 >> State(Running)\n"
            "  _ >> state\n"
            "machine Controller(state:State,value:u64)\n"
            "  select=state.mode\n"
            "  init=State(Idle)\n"
            "  next=next(state,value)\n"
            "  success=Running\n"
            "  failure=Idle\n"
        )
        _, coverage = _coverage(source)
        result = coverage[0]
        concrete = 2 * (1 << 64)
        self.assertTrue(result.partitioned)
        self.assertEqual(result.input_cardinality, str(1 << 64))
        self.assertEqual(result.possible_pairs, str(concrete))
        self.assertEqual(result.region_count, 4)
        self.assertEqual(result.defined_pairs, 2)
        self.assertEqual(result.fallthrough_pairs, concrete - 2)
        self.assertEqual(result.unknown_pairs, 0)
        self.assertTrue(result.complete)
        self.assertTrue(result.exact)

    def test_large_product_groups_unobserved_finite_fields(self) -> None:
        source = (
            "resource Token[Ready]\n"
            "+Mode=Idle|Running\n"
            "*Input(active:bool,b:bool,c:bool,d:bool,e:bool,f:bool,g:bool,h:bool,i:bool,j:bool)\n"
            "*State(mode:Mode)\n"
            ">next(state:State,input:Input):State\n"
            "  input.active==true >> State(Running)\n"
            "  _ >> state\n"
            "machine Controller(state:State,input:Input)\n"
            "  select=state.mode\n"
            "  init=State(Idle)\n"
            "  next=next(state,input)\n"
            "  success=Running\n"
            "  failure=Idle\n"
        )
        _, coverage = _coverage(source)
        result = coverage[0]
        self.assertTrue(result.partitioned)
        self.assertEqual(result.input_cardinality, "1024")
        self.assertEqual(result.possible_pairs, "2048")
        self.assertEqual(result.region_count, 4)
        self.assertEqual(result.defined_pairs, 1024)
        self.assertEqual(result.fallthrough_pairs, 1024)
        self.assertEqual(result.unknown_pairs, 0)
        self.assertTrue(result.complete)
        self.assertTrue(result.exact)

    def test_unsupported_integer_arithmetic_remains_unknown(self) -> None:
        source = (
            "resource Token[Ready]\n"
            "+Mode=Idle|Running\n"
            "*State(mode:Mode)\n"
            ">next(state:State,value:u8):State\n"
            "  value+1<10 >> State(Running)\n"
            "  _ >> state\n"
            "machine Controller(state:State,value:u8)\n"
            "  select=state.mode\n"
            "  init=State(Idle)\n"
            "  next=next(state,value)\n"
            "  success=Running\n"
            "  failure=Idle\n"
        )
        algebra, coverage = _coverage(source)
        result = coverage[0]
        self.assertTrue(result.partitioned)
        self.assertEqual(result.missing_pairs, "0")
        self.assertEqual(result.unknown_pairs, 512)
        self.assertFalse(result.complete)
        self.assertFalse(result.exact)
        payload = tooling_payload(
            algebra.diagnostics,
            algebra.structural_conversions,
            coverage,
        )
        codes = {item["code"] for item in payload["diagnostics"]}
        self.assertIn("machine-coverage-unknown", codes)
        self.assertNotIn("machine-coverage-missing", codes)


if __name__ == "__main__":
    unittest.main()

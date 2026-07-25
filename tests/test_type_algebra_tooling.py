from __future__ import annotations

import json
import unittest

from glyph import compile_outputs, parse_compilation_model
from glyph.execution_ir import build_execution_structure_ir
from glyph.type_algebra import build_machine_coverage, build_type_algebra_ir


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

    def test_machine_coverage_reports_finite_state_input_space(self) -> None:
        source = (
            "resource Token[Ready]\n"
            "+Mode=Idle|Running\n"
            "+Event=Start|Stop\n"
            "*State(mode:Mode)\n"
            ">next(state:State,event:Event):State=state\n"
            "machine Controller(state:State,event:Event)\n"
            "  select=state.mode\n"
            "  init=State(Idle)\n"
            "  next=next(state,event)\n"
            "  success=Running\n"
            "  failure=Idle\n"
        )
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
        self.assertEqual(len(coverage), 1)
        self.assertEqual(coverage[0].state_cardinality, "2")
        self.assertEqual(coverage[0].input_cardinality, "2")
        self.assertEqual(coverage[0].possible_pairs, "4")


if __name__ == "__main__":
    unittest.main()

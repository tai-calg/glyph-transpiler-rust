from __future__ import annotations

import json
import unittest

from glyph.mermaid import compile_diagram_bundle
from glyph.studio_ui import STUDIO_HTML


SOURCE = "\n".join(
    [
        "@MAX=100",
        "+Command=Stop|Run(U)|Fault",
        "+Error=Bad",
        ">validate(x:U):U|Error=Ok(x)",
        "~optimize(x:U):U # TODO: O(n log n) Rust implementation",
        "!emit(x:U):U=x",
        ">process(c:Command):U|Error",
        "  speed :=",
        "    c==Stop >> 0",
        "    c==Run(n) >> n",
        "    c==Fault >> 0",
        "    _ >> 0",
        "",
        "  checked :=",
        "    speed",
        "    /> validate?",
        "",
        "  normalized :=",
        "    checked",
        "    /> |n| min(n,MAX)",
        "    /> optimize",
        "",
        "  emitted :=",
        "    normalized",
        "    /> emit",
        "",
        "  Ok(emitted)",
    ]
) + "\n"


class AlgorithmIRTests(unittest.TestCase):
    def test_algorithm_ir_preserves_source_structure_and_types(self) -> None:
        bundle = compile_diagram_bundle(SOURCE, "algorithm.glyph")
        payload = json.loads(bundle.files["algorithm-ir.json"])
        self.assertEqual(payload["source_name"], "algorithm.glyph")
        self.assertEqual(len(payload["functions"]), 1)

        function = payload["functions"][0]
        self.assertEqual(function["name"], "process")
        self.assertEqual(function["return_type"], "R<u16,Error>")
        self.assertEqual(function["source"]["line"], 7)
        self.assertEqual(
            [step["name"] for step in function["steps"][:-1]],
            ["speed", "checked", "normalized", "emitted"],
        )

        speed = function["steps"][0]
        self.assertEqual(speed["value"]["kind"], "conditional")
        run_branch = speed["value"]["branches"][1]
        self.assertEqual(run_branch["condition"], "c==Run(n)")
        self.assertEqual(run_branch["binders"], ["n"])
        self.assertEqual(run_branch["source"]["line"], 10)

        checked_stage = function["steps"][1]["value"]["stages"][0]
        self.assertEqual(checked_stage["name"], "validate")
        self.assertTrue(checked_stage["propagates"])
        self.assertEqual(checked_stage["input_type"], "u16")
        self.assertEqual(checked_stage["output_type"], "u16")
        self.assertEqual(checked_stage["source"]["line"], 16)

        normalized_stages = function["steps"][2]["value"]["stages"]
        self.assertEqual(
            [stage["kind"] for stage in normalized_stages], ["lambda", "rust"]
        )
        self.assertEqual(normalized_stages[0]["label"], "λ n → min(n,100)")
        self.assertEqual(normalized_stages[0]["source"]["line"], 20)
        self.assertEqual(normalized_stages[1]["name"], "optimize")
        self.assertEqual(normalized_stages[1]["source"]["line"], 21)

        emitted_stage = function["steps"][3]["value"]["stages"][0]
        self.assertEqual(emitted_stage["kind"], "effect")
        self.assertEqual(emitted_stage["source"]["line"], 25)

    def test_logic_artifacts_hide_compiler_helpers(self) -> None:
        bundle = compile_diagram_bundle(SOURCE, "algorithm.glyph")
        self.assertIn("logic.mmd", bundle.files)
        self.assertIn("algorithm-ir.json", bundle.files)
        self.assertNotIn("__glyph_", bundle.files["logic.mmd"])
        self.assertNotIn("__glyph_", bundle.files["algorithm-ir.json"])
        self.assertIn("λ n → min(n,100)", bundle.files["logic.mmd"])
        self.assertIn(
            "class algorithm_process_0_step_2_stage_1 rust",
            bundle.files["logic.mmd"],
        )
        self.assertIn("Err", bundle.files["logic.mmd"])

    def test_source_map_points_algorithm_items_to_logic_view(self) -> None:
        bundle = compile_diagram_bundle(SOURCE, "algorithm.glyph")
        source_map = json.loads(bundle.files["source-map.json"])["line_to_views"]
        self.assertTrue(
            any(item["diagram"] == "logic.mmd" for item in source_map["20"])
        )
        self.assertTrue(
            any(item["kind"] == "algorithm-rust" for item in source_map["21"])
        )
        self.assertTrue(
            any(item["kind"] == "algorithm-effect" for item in source_map["25"])
        )

    def test_studio_reads_algorithm_ir_and_supports_source_navigation(self) -> None:
        self.assertIn("algorithm-ir.json", STUDIO_HTML)
        self.assertIn("function goLine", STUDIO_HTML)
        self.assertIn("async function logic", STUDIO_HTML)
        self.assertIn("function renderPipeline", STUDIO_HTML)
        self.assertIn("data-line-action", STUDIO_HTML)
        self.assertIn("entityAttr('function:'+fn.name)", STUDIO_HTML)


if __name__ == "__main__":
    unittest.main()

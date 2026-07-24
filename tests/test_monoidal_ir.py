from __future__ import annotations

import json
import unittest

from glyph import compile_outputs


class MonoidalIRTests(unittest.TestCase):
    def test_pure_product_constructor_emits_tensor_and_parallel_nodes(self) -> None:
        outputs = compile_outputs(
            "*Input(raw:U,voltage:F)\n"
            "*Output(frame:U,reading:F)\n"
            ">decode(x:U):U=x\n"
            ">measure(x:F):F=x\n"
            ">process(x:Input):Output=Output(decode(x.raw),measure(x.voltage))\n",
            "parallel.glyph",
        )

        payload = json.loads(outputs.diagrams.files["monoidal-ir.json"])
        value_tensor = next(
            tensor
            for tensor in payload["tensors"]
            if tensor["role"] == "product_value" and tensor["function"] == "process"
        )
        parallel = next(
            item for item in payload["parallels"] if item["tensor_id"] == value_tensor["id"]
        )

        self.assertEqual(payload["schema"], "glyph.monoidal-ir")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(value_tensor["product_type"], "Output")
        self.assertEqual(
            [factor["name"] for factor in value_tensor["factors"]],
            ["frame", "reading"],
        )
        self.assertEqual(
            [lane["calls"] for lane in parallel["lanes"]],
            [["decode"], ["measure"]],
        )
        self.assertIn("structural-independent", parallel["semantics"])
        self.assertIn("Parallel", outputs.diagrams.files["monoidal.mmd"])
        self.assertIn("⊗ Output value", outputs.diagrams.files["monoidal.mmd"])

        source_map = json.loads(outputs.diagrams.files["source-map.json"])
        monoidal_entries = [
            entry
            for entries in source_map["line_to_views"].values()
            for entry in entries
            if entry["diagram"] == "monoidal.mmd"
        ]
        self.assertTrue(monoidal_entries)

    def test_try_lane_is_not_reclassified_as_unordered_parallel_work(self) -> None:
        outputs = compile_outputs(
            "+E=Bad\n"
            "*Pair(left:U,right:U)\n"
            ">check(x:U):U|E=Ok(x)\n"
            ">build(x:U):Pair|E=Ok(Pair(check(x)?,x))\n",
            "try.glyph",
        )

        payload = json.loads(outputs.diagrams.files["monoidal-ir.json"])
        tensor = next(
            item
            for item in payload["tensors"]
            if item["role"] == "product_value" and item["function"] == "build"
        )

        self.assertNotIn(
            tensor["id"],
            {parallel["tensor_id"] for parallel in payload["parallels"]},
        )

    def test_multiple_resource_capabilities_emit_tensor_boundaries(self) -> None:
        outputs = compile_outputs(
            "resource Buffer[Ready|InFlight]\n"
            "resource Fence[Pending|Complete]\n"
            "*Submission(buffer:own Buffer[InFlight],fence:own Fence[Pending])\n"
            "!submit(buffer:own Buffer[Ready],fence:own Fence[Pending]):Submission\n",
            "resources.glyph",
        )

        payload = json.loads(outputs.diagrams.files["monoidal-ir.json"])
        resource_tensors = [
            tensor
            for tensor in payload["tensors"]
            if tensor["resource"] and tensor["function"] == "submit"
        ]

        self.assertEqual(
            {tensor["role"] for tensor in resource_tensors},
            {"resource_input", "resource_output"},
        )
        input_tensor = next(
            tensor for tensor in resource_tensors if tensor["role"] == "resource_input"
        )
        self.assertEqual(
            [factor["capability"] for factor in input_tensor["factors"]],
            ["own", "own"],
        )
        self.assertEqual(
            [factor["state"] for factor in input_tensor["factors"]],
            ["Ready", "Pending"],
        )
        self.assertEqual(payload["parallels"], [])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest

from glyph import compile_outputs


class TypeAlgebraIRTests(unittest.TestCase):
    def test_cardinality_impossibility_isomorphism_and_conversions(self) -> None:
        outputs = compile_outputs(
            "resource Token[Ready]\n"
            "+Bit=Off|On\n"
            "*Pair(left:Bit,right:Bit)\n"
            "+Quad=Q0|Q1|Q2|Q3\n"
            "*Impossible(value:Never)\n",
            "finite.glyph",
        )

        payload = json.loads(outputs.diagrams.files["type-algebra-ir.json"])
        types = {item["name"]: item for item in payload["types"]}

        self.assertEqual(payload["schema"], "glyph.type-algebra-ir")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(types["Bit"]["cardinality"], "2")
        self.assertEqual(types["Pair"]["cardinality"], "4")
        self.assertEqual(types["Quad"]["cardinality"], "4")
        self.assertEqual(len(types["Pair"]["exhaustive_cases"]), 4)
        self.assertTrue(types["Impossible"]["impossible"])
        self.assertEqual(types["Impossible"]["normal_form"], "0")
        self.assertEqual(types["Impossible"]["cardinality"], "0")

        pair_class = next(
            item
            for item in payload["isomorphism_classes"]
            if item["members"] == ["Pair", "Quad"]
        )
        self.assertEqual(pair_class["normal_form"], "4")
        self.assertEqual(pair_class["cardinality"], "4")
        self.assertEqual(
            set(pair_class["conversions"]),
            {
                "glyph_convert_pair_to_quad",
                "glyph_convert_quad_to_pair",
            },
        )

        generated = outputs.diagrams.files["type-algebra.generated.rs"]
        self.assertIn("pub fn glyph_convert_pair_to_quad", generated)
        self.assertIn("pub fn glyph_convert_quad_to_pair", generated)
        self.assertIn("Pair { left: Bit::Off, right: Bit::Off }", generated)
        self.assertIn("Quad::Q0", generated)
        self.assertIn("roundtrip_pair_quad", generated)

    def test_distributive_normal_form_detects_symbolic_isomorphism(self) -> None:
        outputs = compile_outputs(
            "resource Token[Ready]\n"
            "+AorB=HasA(A)|HasB(B)\n"
            "*Left(x:X,choice:AorB)\n"
            "*XA(x:X,a:A)\n"
            "*XB(x:X,b:B)\n"
            "+Right=InA(XA)|InB(XB)\n",
            "distribution.glyph",
        )

        payload = json.loads(outputs.diagrams.files["type-algebra-ir.json"])
        types = {item["name"]: item for item in payload["types"]}
        self.assertEqual(types["Left"]["normal_form"], "A * X + B * X")
        self.assertEqual(types["Right"]["normal_form"], "A * X + B * X")
        self.assertFalse(types["Left"]["cardinality_exact"])

        iso = next(
            item
            for item in payload["isomorphism_classes"]
            if item["members"] == ["Left", "Right"]
        )
        self.assertEqual(iso["conversions"], [])
        rejected = [
            item
            for item in payload["conversions"]
            if {item["source_type"], item["target_type"]}
            == {"Left", "Right"}
        ]
        self.assertEqual(len(rejected), 2)
        self.assertTrue(all(not item["generated"] for item in rejected))

    def test_recursive_types_remain_symbolic_and_are_not_finitely_enumerated(self) -> None:
        outputs = compile_outputs(
            "resource Token[Ready]\n"
            "+List=Nil|Cons(bool,List)\n",
            "recursive.glyph",
        )

        payload = json.loads(outputs.diagrams.files["type-algebra-ir.json"])
        analysis = next(item for item in payload["types"] if item["name"] == "List")
        self.assertIn("recursive<List>", analysis["normal_form"])
        self.assertFalse(analysis["cardinality_exact"])
        self.assertFalse(analysis["exhaustive_complete"])
        self.assertEqual(analysis["exhaustive_cases"], [])

    def test_legacy_artifact_set_is_unchanged(self) -> None:
        outputs = compile_outputs(
            "+Bit=Off|On\n"
            "*Pair(left:Bit,right:Bit)\n",
            "legacy.glyph",
        )

        self.assertNotIn("type-algebra-ir.json", outputs.diagrams.files)
        self.assertNotIn("type-algebra.generated.rs", outputs.diagrams.files)


if __name__ == "__main__":
    unittest.main()

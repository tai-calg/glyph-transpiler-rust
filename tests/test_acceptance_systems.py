from __future__ import annotations

import unittest

from glyph.compiler import ExternDecl
from tests.acceptance_support import compile_example, load, stages


class AcceptanceSystemTests(unittest.TestCase):
    def test_door_connects_architecture_machine_and_time(self) -> None:
        outputs = compile_example("door")
        architecture = load(outputs, "architecture-ir.json")
        execution = load(outputs, "execution-ir.json")
        self.assertEqual([item["name"] for item in architecture["systems"]], ["DoorController"])
        self.assertEqual([item["name"] for item in execution["machines"]], ["Door"])
        self.assertEqual(
            {item["name"] for item in execution["temporal"]},
            {"lock_deadline", "forced_open_safe"},
        )
        mapping = load(outputs, "preprocessor-map.json")
        self.assertTrue(any("DOOR_FLOW" in item["macro_stack"] for item in mapping["expanded_lines"]))

    def test_batch_separates_rust_effect_and_error_paths(self) -> None:
        outputs = compile_example("batch")
        items = stages(load(outputs, "algorithm-ir.json"))
        by_name = {item["name"]: item for item in items if item.get("name")}
        self.assertEqual(by_name["layout_lane"]["kind"], "rust")
        self.assertEqual(by_name["submit_batch"]["kind"], "effect")
        self.assertTrue(any(item["propagates"] for item in items))
        self.assertIn("Err", outputs.diagrams.files["logic.mmd"])
        self.assertIn("pub fn layout_lane", outputs.artifacts.manual_scaffold)
        opaque = {item.name for item in outputs.model.opaques}
        effects = {
            item.name
            for item in outputs.model.program.declarations
            if isinstance(item, ExternDecl) and item.name not in opaque
        }
        self.assertEqual(opaque, {"layout_lane"})
        self.assertEqual(effects, {"submit_batch"})

    def test_motor_has_one_effect_and_safety_constraints(self) -> None:
        outputs = compile_example("motor")
        effects = {
            item.name
            for item in outputs.model.program.declarations
            if isinstance(item, ExternDecl)
        }
        self.assertEqual(effects, {"write_motor"})
        execution = load(outputs, "execution-ir.json")
        self.assertEqual([item["name"] for item in execution["machines"]], ["Motor"])
        self.assertEqual(
            {item["name"] for item in execution["temporal"]},
            {"emergency_stop", "fault_stop"},
        )


if __name__ == "__main__":
    unittest.main()

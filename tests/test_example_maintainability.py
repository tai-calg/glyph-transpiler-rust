from __future__ import annotations

from pathlib import Path
import re
import unittest

from glyph import compile_outputs


ROOT = Path(__file__).resolve().parents[1]
MAINTAINED_EXAMPLES = (
    ROOT / "examples" / "acceptance" / "door_controller.glyph",
    ROOT / "examples" / "acceptance" / "job_scheduler.glyph",
    ROOT / "examples" / "acceptance" / "motor_safety.glyph",
    ROOT / "examples" / "door_sketch.glyph",
    ROOT / "examples" / "system_controller.glyph",
    ROOT / "examples" / "temperature_view.glyph",
)
OLD_SYSTEM_ENTRY = re.compile(r"(?m)^system\s+[A-Za-z_]\w*\s*=")


class ExampleMaintainabilityTests(unittest.TestCase):
    def test_maintained_examples_use_checked_system_context_and_compile(self) -> None:
        for path in MAINTAINED_EXAMPLES:
            with self.subTest(path=path.relative_to(ROOT)):
                source = path.read_text(encoding="utf-8")
                self.assertIsNone(OLD_SYSTEM_ENTRY.search(source))
                self.assertRegex(source, r"(?m)^system\s+[A-Za-z_]\w*\s*$")
                self.assertRegex(source, r"(?m)^\s+entry\s+[A-Za-z_]\w*\s*$")
                self.assertRegex(source, r"(?m)^\s+in\s+[A-Za-z_]\w*:")
                self.assertRegex(source, r"(?m)^\s+out\s+[A-Za-z_]\w*:")
                outputs = compile_outputs(source, str(path.relative_to(ROOT)))
                self.assertTrue(outputs.artifacts.logic)
                self.assertTrue(outputs.diagrams.files["architecture-ir.json"])

    def test_example_names_match_their_design_responsibility(self) -> None:
        motor = (ROOT / "examples" / "acceptance" / "motor_safety.glyph").read_text(
            encoding="utf-8"
        )
        temperature = (ROOT / "examples" / "temperature_view.glyph").read_text(
            encoding="utf-8"
        )
        self.assertIn("*MotorState", motor)
        self.assertIn("!write_motor", motor)
        self.assertNotIn("TemperatureInput", motor)
        self.assertIn("*TemperatureInput", temperature)
        self.assertIn(">to_fahrenheit", temperature)
        self.assertNotIn("write_motor", temperature)

    def test_principal_execution_paths_are_not_hidden_in_raw_macros(self) -> None:
        door = (ROOT / "examples" / "acceptance" / "door_controller.glyph").read_text(
            encoding="utf-8"
        )
        motor = (ROOT / "examples" / "acceptance" / "motor_safety.glyph").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("@DOOR_FLOW", door)
        self.assertNotIn("@NORMALIZE", motor)
        self.assertIn(">control(state:DoorState)", door)
        self.assertIn(">normalize(raw:F):F", motor)

    def test_demo_exposes_a_selective_facade(self) -> None:
        library = (ROOT / "demo-system" / "src" / "lib.rs").read_text(encoding="utf-8")
        controller = (ROOT / "demo-system" / "src" / "controller.rs").read_text(
            encoding="utf-8"
        )
        host = (ROOT / "demo-system" / "src" / "host.rs").read_text(encoding="utf-8")

        self.assertNotRegex(library, r"(?m)^pub\s+mod\s+")
        self.assertNotIn("pub use generated::{Cycle", library)
        self.assertNotIn("Receipt, System", library)
        self.assertIn("SystemSnapshot", library)
        self.assertIn("ReceiptSnapshot", library)
        self.assertIn("pub struct StepOutcome", controller)
        self.assertNotRegex(controller, r"pub struct StepOutcome\s*\{\s*pub ")
        self.assertNotRegex(host, r"(?m)^pub\s+fn\s+")
        self.assertIn("#[cfg(test)]\npub(crate) fn fail_next_write", host)

    def test_repository_contains_no_migration_or_packaging_residue(self) -> None:
        self.assertFalse((ROOT / ".github" / "refactor-payload").exists())
        self.assertFalse((ROOT / ".github" / "system-boundary-payload.txt").exists())
        self.assertFalse(
            (ROOT / ".github" / "workflows" / "apply-system-boundary-pr.yml").exists()
        )
        self.assertFalse(list(ROOT.glob("*.egg-info")))
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.egg-info/", gitignore)
        self.assertIn("demo-system/target/", gitignore)


if __name__ == "__main__":
    unittest.main()

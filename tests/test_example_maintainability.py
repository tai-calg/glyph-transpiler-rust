from __future__ import annotations

from pathlib import Path
import re
import unittest

from glyph import compile_outputs


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SYSTEM_SOURCES = tuple(
    sorted((ROOT / "examples").rglob("*.glyph"))
    + [ROOT / "glyph" / "resources" / "default.glyph"]
)
OLD_SYSTEM_ENTRY = re.compile(r"(?m)^system\s+[A-Za-z_]\w*\s*=")
SYSTEM_HEADER = re.compile(r"^system\s+([A-Za-z_]\w*)\s*$")
SYSTEM_ITEM = re.compile(r"^(entry|source|sink)\s+([A-Za-z_]\w*)\s*$")


def system_blocks(source: str) -> list[tuple[str, list[str]]]:
    lines = source.splitlines()
    blocks: list[tuple[str, list[str]]] = []
    index = 0
    while index < len(lines):
        header = SYSTEM_HEADER.fullmatch(lines[index])
        if header is None:
            index += 1
            continue
        items: list[str] = []
        cursor = index + 1
        while cursor < len(lines):
            raw = lines[cursor]
            code = raw.split("#", 1)[0].rstrip()
            if not code:
                cursor += 1
                continue
            if not code[:1].isspace():
                break
            items.append(code.strip())
            cursor += 1
        blocks.append((header.group(1), items))
        index = cursor
    return blocks


class ExampleMaintainabilityTests(unittest.TestCase):
    def test_all_public_system_examples_use_entry_source_sink_and_compile(self) -> None:
        checked = 0
        for path in PUBLIC_SYSTEM_SOURCES:
            source = path.read_text(encoding="utf-8")
            blocks = system_blocks(source)
            if not blocks:
                continue
            checked += 1
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsNone(OLD_SYSTEM_ENTRY.search(source))
                for name, items in blocks:
                    self.assertTrue(items, f"system {name} has no boundary items")
                    parsed = [SYSTEM_ITEM.fullmatch(item) for item in items]
                    self.assertTrue(
                        all(item is not None for item in parsed),
                        f"system {name} contains a non-canonical item: {items}",
                    )
                    roles = [item.group(1) for item in parsed if item is not None]
                    self.assertEqual(
                        roles.count("entry"),
                        1,
                        f"system {name} must declare exactly one entry",
                    )

                outputs = compile_outputs(source, str(path.relative_to(ROOT)))
                self.assertTrue(outputs.artifacts.logic)
                architecture = outputs.model.architecture
                self.assertEqual(len(architecture.systems), len(blocks))
                for system in architecture.systems:
                    self.assertEqual(system.ports, ())
                    self.assertTrue(system.components)
                    self.assertTrue(
                        all(
                            component.role in {"entry", "source", "sink", "internal"}
                            for component in system.components
                        )
                    )
                    self.assertTrue(all(edge.kind == "call" for edge in system.edges))
                    self.assertTrue(
                        all(evidence.kind == "call" for evidence in system.evidence)
                    )
        self.assertGreaterEqual(checked, 9)

    def test_public_documentation_teaches_the_canonical_system_boundary(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        language = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        io_app = (ROOT / "docs" / "IO_STATE_APP.md").read_text(encoding="utf-8")

        canonical = """system MotorSafety
  entry cycle
  source sensor
  sink write_motor"""
        self.assertIn("## 10. System境界", readme)
        self.assertIn(canonical, readme)
        self.assertIn("矢印は常に関数呼出しだけ", readme)
        self.assertNotIn("## 10. System Context", readme)
        self.assertNotIn("System Context: input ->", readme)
        self.assertNotIn("| `->` | `system`内 | 公開境界上のflow |", readme)
        self.assertNotIn("公開I/Oと作用flowを宣言する", readme)

        self.assertIn("### System boundary", language)
        self.assertIn('system               := "system" Name', language)
        self.assertIn('system-entry         := "entry" Name', language)
        self.assertIn('system-source        := "source" Name', language)
        self.assertIn('system-sink          := "sink" Name', language)
        self.assertIn("Reachable `>` and `~` functions are internal nodes", language)

        self.assertIn("## Executable System boundary view", io_app)
        self.assertIn("Function calls only", io_app)
        self.assertIn("`~optimize`はHost側で実装する純粋関数", io_app)

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
        for path in (
            ROOT / ".github" / "workflows" / "apply-system-boundary-pr.yml",
            ROOT / ".github" / "workflows" / "update-readme-state-snapshot.yml",
            ROOT / ".github" / "workflows" / "update-system-boundary-docs.yml",
            ROOT / "scripts" / "migrate_system_boundary_docs_once.py",
        ):
            self.assertFalse(path.exists(), f"temporary migration file remains: {path}")
        self.assertFalse(list(ROOT.glob("*.egg-info")))
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.egg-info/", gitignore)
        self.assertIn("demo-system/target/", gitignore)


if __name__ == "__main__":
    unittest.main()

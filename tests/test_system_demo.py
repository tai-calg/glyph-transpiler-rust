from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

from glyph import compile_artifacts


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples" / "system_controller.glyph"
LOGIC = ROOT / "demo-system" / "src" / "generated.rs"
HOST_STUB = ROOT / "demo-system" / "src" / "host.generated.rs"


class SystemDemoGenerationTests(unittest.TestCase):
    def test_generation_is_deterministic_and_contains_all_layers(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        first = compile_artifacts(source)
        second = compile_artifacts(source)

        self.assertEqual(first, second)
        self.assertIn("pub struct Input", first.logic)
        self.assertIn("pub fn transition", first.logic)
        self.assertIn("if let Command::Run", first.logic)
        self.assertIn("pub struct AckDeadlineStreamingMonitor", first.logic)
        self.assertIn("pub struct HeartbeatLiveStreamingMonitor", first.logic)
        self.assertIn("pub struct AuthorizationSafeStreamingMonitor", first.logic)
        self.assertIn("// effect boundary: write_actuator", first.logic)
        self.assertIn("pub fn write_actuator", first.host)
        self.assertIn("pub fn report_violation", first.host)

    @unittest.skipUnless(shutil.which("cargo"), "cargoがない環境ではRust側テストを省略")
    def test_generated_system_demo_compiles_and_passes(self) -> None:
        artifacts = compile_artifacts(SOURCE.read_text(encoding="utf-8"))
        LOGIC.write_text(artifacts.logic, encoding="utf-8")
        HOST_STUB.write_text(artifacts.host, encoding="utf-8")

        subprocess.run(
            [
                "cargo",
                "test",
                "--manifest-path",
                str(ROOT / "demo-system" / "Cargo.toml"),
            ],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

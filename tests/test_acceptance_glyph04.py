from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from glyph import compile_outputs


ROOT = Path(__file__).resolve().parents[1]


class Glyph04AcceptanceTests(unittest.TestCase):
    def test_complete_glyph04_system_generates_all_layers(self) -> None:
        source = (ROOT / "examples" / "acceptance" / "glyph04_system.glyph").read_text(
            encoding="utf-8"
        )
        first = compile_outputs(source, "glyph04_system.glyph")
        second = compile_outputs(source, "glyph04_system.glyph")

        self.assertEqual(first.artifacts, second.artifacts)
        self.assertEqual(first.design_json, second.design_json)
        self.assertIn("capability-ir.json", first.diagrams.files)
        self.assertIn("contracts-ir.json", first.diagrams.files)
        self.assertIn("runtime-contract-ir.json", first.diagrams.files)
        self.assertIn("verification-report.json", first.diagrams.files)
        self.assertIn("ContractObservationSafeObservationStreamingMonitor", first.artifacts.logic)

        capability = json.loads(first.diagrams.files["capability-ir.json"])
        runtime = json.loads(first.diagrams.files["runtime-contract-ir.json"])
        verification = json.loads(first.diagrams.files["verification-report.json"])

        self.assertEqual(capability["resources"][0]["name"], "Buffer")
        self.assertTrue(any(item["target"] == "normalize" for item in runtime["applications"]))
        self.assertGreater(verification["summary"]["static"], 0)
        self.assertGreater(verification["summary"]["trusted"], 0)

        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory) / "generated.rs"
            generated.write_text(first.artifacts.logic, encoding="utf-8")
            subprocess.run(
                [
                    "rustc",
                    "--edition",
                    "2021",
                    "--crate-type",
                    "lib",
                    str(generated),
                    "-o",
                    str(Path(directory) / "libglyph04.rlib"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()

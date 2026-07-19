from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_check_mode(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "glyphc.py"), str(ROOT / "examples" / "controller.glyph"), "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK:", result.stdout)

    def test_output_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generated.rs"
            host_output = Path(directory) / "host.generated.rs"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "glyphc.py"),
                    str(ROOT / "examples" / "controller.glyph"),
                    "-o",
                    str(output),
                    "--host-output",
                    str(host_output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.exists())
            self.assertTrue(host_output.exists())
            self.assertIn("pub fn run", output.read_text(encoding="utf-8"))
            self.assertIn("pub fn exec", host_output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

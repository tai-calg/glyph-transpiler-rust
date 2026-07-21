from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DevelopmentCliTests(unittest.TestCase):
    def test_ast_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "typed-ast.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "glyphc.py"),
                    str(ROOT / "examples" / "lisp_core.glyph"),
                    "--ast-json",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertIn("symbols", data)
            self.assertTrue(any(item["name"] == "apply" for item in data["functions"]))

    def test_watch_once_updates_diagrams_and_ast(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diagrams = root / "diagrams"
            ast = root / "typed-ast.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "glyphc.py"),
                    str(ROOT / "examples" / "lisp_core.glyph"),
                    "--watch-once",
                    "--diagram-dir",
                    str(diagrams),
                    "--ast-json",
                    str(ast),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((diagrams / "execution.mmd").exists())
            self.assertTrue(ast.exists())

    def test_repl_scripted_session(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "glyphc.py"),
                str(ROOT / "examples" / "lisp_core.glyph"),
                "--repl",
            ],
            input=":type apply\n:ast sum\n:quit\n",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Fn", result.stdout)
        self.assertIn('"recursion"', result.stdout)


if __name__ == "__main__":
    unittest.main()

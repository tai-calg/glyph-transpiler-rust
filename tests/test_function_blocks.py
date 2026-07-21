from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph import GlyphError, compile_artifacts, parse_compilation_model


class FunctionBlockTests(unittest.TestCase):
    def test_bindings_generate_direct_rust_lets(self) -> None:
        source = """
+Command=Stop|Run(U)|Fault
>double(x:U):U=x*2
>process(c:Command):U
  speed :=
    c==Stop >> 0
    c==Run(n) >> n
    _ >> 0

  limited :=
    speed>100 >> 100
    _ >> speed

  normalized :=
    limited
    /> |n| n+1
    /> double

  result :=
    normalized==0 >> 1
    _ >> normalized

  result
"""
        artifacts = compile_artifacts(source)
        rust = artifacts.logic
        self.assertIn("let speed = {", rust)
        self.assertIn("let limited = {", rust)
        self.assertIn("let normalized = double(__glyph_block_lambda", rust)
        self.assertIn("let result = {", rust)
        self.assertNotIn("pub fn __glyph_block_L", rust)

        model = parse_compilation_model(source)
        self.assertEqual(len(model.blocks), 1)
        self.assertEqual(
            [item.name for item in model.blocks[0].bindings],
            ["speed", "limited", "normalized", "result"],
        )

    def test_question_propagation_inside_binding(self) -> None:
        source = """
+Error=Bad
>validate(x:U):U|Error=Ok(x)
>checked(x:U):U|Error
  value := validate(x)?
  Ok(value)
"""
        rust = compile_artifacts(source).logic
        self.assertIn("let value = validate(x)?;", rust)
        self.assertIn("Ok(value)", rust)

    def test_binding_name_is_single_assignment(self) -> None:
        source = """
>bad(x:U):U
  value := x+1
  value := value+1
  value
"""
        with self.assertRaisesRegex(GlyphError, "既に定義済み"):
            compile_artifacts(source)

    def test_block_requires_final_expression(self) -> None:
        source = """
>bad(x:U):U
  value := x+1
"""
        with self.assertRaisesRegex(GlyphError, "最後に返す式"):
            compile_artifacts(source)

    def test_conditional_binding_requires_fallback(self) -> None:
        source = """
>bad(x:U):U
  value :=
    x>0 >> x
  value
"""
        with self.assertRaisesRegex(GlyphError, "'_' 節"):
            compile_artifacts(source)

    def test_generated_block_compiles_with_rustc(self) -> None:
        source = """
+Command=Stop|Run(U)|Fault
+Error=Bad
>double(x:U):U=x*2
>validate(x:U):U|Error=Ok(x)
>process(c:Command):U
  speed :=
    c==Stop >> 0
    c==Run(n) >> n
    _ >> 0
  normalized :=
    speed
    /> |n| n+1
    /> double
  normalized
>checked(x:U):U|Error
  value := validate(x)?
  Ok(value)
"""
        rust = compile_artifacts(source).logic
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "generated.rs"
            output_path = Path(directory) / "libglyph_block.rlib"
            source_path.write_text(rust, encoding="utf-8")
            completed = subprocess.run(
                [
                    "rustc",
                    "--edition",
                    "2021",
                    "--crate-type",
                    "lib",
                    str(source_path),
                    "-o",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()

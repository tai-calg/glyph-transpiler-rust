from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from glyph.compilation import CompilationPipeline
from glyph.ui_ir import (
    UI_IR_SCHEMA,
    UI_IR_VERSION,
    UiIrError,
    build_ui_application,
)


ROOT = Path(__file__).resolve().parents[1]


def compile_example(name: str):
    path = ROOT / "examples" / name
    source = path.read_text(encoding="utf-8")
    return path, CompilationPipeline().compile_text(source, source_name=str(path))


class UiIrTests(unittest.TestCase):
    def test_temperature_signature_projects_without_temperature_special_cases(self) -> None:
        path, compilation = compile_example("gradio_temperature.glyph")
        app = build_ui_application(
            compilation.model,
            source_name=str(path),
        )

        self.assertEqual(app.action.name, "render")
        self.assertEqual(app.to_dict()["schema"], UI_IR_SCHEMA)
        self.assertEqual(app.to_dict()["version"], UI_IR_VERSION)
        self.assertEqual(app.action.inputs[0].kind, "object")
        self.assertEqual(app.action.inputs[0].children[0].kind, "number")
        output_by_name = {
            child.path[-1]: child for child in app.action.output.children
        }
        self.assertEqual(output_by_name["fahrenheit"].kind, "metric")
        self.assertEqual(output_by_name["valid"].kind, "status")
        self.assertEqual(output_by_name["band"].kind, "badge")

    def test_profile_projects_text_integer_boolean_and_unit_sum(self) -> None:
        path, compilation = compile_example("gradio_profile.glyph")
        app = build_ui_application(compilation.model, source_name=str(path))

        profile = app.action.inputs[0]
        self.assertEqual(profile.kind, "object")
        kinds = {child.path[-1]: child.kind for child in profile.children}
        self.assertEqual(
            kinds,
            {"name": "text", "age": "integer", "active": "checkbox"},
        )
        output = {child.path[-1]: child for child in app.action.output.children}
        self.assertEqual(output["access"].kind, "badge")
        self.assertEqual(
            output["access"].choices,
            ("Guest", "Member", "Admin"),
        )

    def test_motor_projects_generic_numeric_controls(self) -> None:
        path, compilation = compile_example("gradio_motor.glyph")
        app = build_ui_application(compilation.model, source_name=str(path))

        input_node = app.action.inputs[0]
        kinds = {child.path[-1]: child.kind for child in input_node.children}
        self.assertEqual(
            kinds,
            {"request": "number", "enabled": "checkbox", "limit": "number"},
        )
        output = {child.path[-1]: child.kind for child in app.action.output.children}
        self.assertEqual(
            output,
            {"command": "metric", "mode": "badge", "safe": "status"},
        )

    def test_entry_selection_requires_explicit_function_when_ambiguous(self) -> None:
        source = ">first(x:U):U=x\n>second(x:U):U=x\n"
        compilation = CompilationPipeline().compile_text(source)
        with self.assertRaisesRegex(UiIrError, "ambiguous"):
            build_ui_application(compilation.model)

        app = build_ui_application(compilation.model, function_name="second")
        self.assertEqual(app.action.name, "second")
        self.assertEqual(app.candidates, ("first", "second"))

    def test_payload_sum_input_uses_explicit_json_boundary(self) -> None:
        source = "+Command=Stop|Run(U)\n>echo(command:Command):Command=command\n"
        compilation = CompilationPipeline().compile_text(source)
        app = build_ui_application(compilation.model)
        node = app.action.inputs[0]

        self.assertEqual(node.kind, "json")
        self.assertEqual(node.choices, ("Stop", "Run"))
        self.assertIn("Payload variants", node.description)
        self.assertEqual(app.action.output.kind, "json")

    def test_ui_ir_is_deterministic(self) -> None:
        path, compilation = compile_example("gradio_profile.glyph")
        first = build_ui_application(compilation.model, source_name=str(path)).to_json()
        second = build_ui_application(compilation.model, source_name=str(path)).to_json()
        self.assertEqual(first, second)
        parsed = json.loads(first)
        self.assertEqual(parsed["schema"], UI_IR_SCHEMA)

    def test_generic_cli_check_does_not_require_gradio_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "profile-ui.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "glyph_gradio.py"),
                    str(ROOT / "examples" / "gradio_profile.glyph"),
                    "--check",
                    "--ui-ir-output",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"schema": "glyph.ui-ir"', completed.stdout)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["version"], 1)


if __name__ == "__main__":
    unittest.main()

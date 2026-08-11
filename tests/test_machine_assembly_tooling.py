from __future__ import annotations

import json
from pathlib import Path
import unittest

from glyph import parse_compilation_model
from glyph.artifacts import build_rust_artifacts
from glyph.assembly_frontend import build_analysis_rust_artifacts
from glyph.compilation import build_design_json, build_diagram_bundle
from glyph.compiler import GlyphError


PLAIN = """\
+Mode=Idle|Running
*State(mode:Mode)
*Input(start:B)

>next(state:State,input:Input):State
  input.start>>State(Running)
  _>>state

machine Controller(state:State,input:Input)
  select=state.mode
  init=State(Idle)
  next=next(state,input)
  success=Running
  failure=Idle
"""


class MachineAssemblyToolingTests(unittest.TestCase):
    def test_design_and_diagram_artifacts_publish_assembly_ir(self) -> None:
        source = Path("examples/machine_assembly_immediate.glyph").read_text(
            encoding="utf-8"
        )
        model = parse_compilation_model(source, "machine_assembly_immediate.glyph")

        design = json.loads(build_design_json(model))
        payload = design["machine_assemblies"]
        self.assertEqual(payload["schema"], "glyph.machine-assembly-set-ir")
        self.assertEqual(payload["version"], 2)
        self.assertEqual(payload["runtime_codegen"]["status"], "blocked")
        self.assertTrue(payload["runtime_codegen"]["fail_closed"])
        assembly = payload["assemblies"][0]
        self.assertEqual(assembly["version"], 2)
        self.assertEqual(assembly["name"], "DoorControl")
        self.assertTrue(assembly["types"])
        self.assertTrue(assembly["instances"][0]["effects"])

        bundle = build_diagram_bundle(model, "machine_assembly_immediate.glyph")
        self.assertIn("machine-assembly-ir.json", bundle.files)
        self.assertIn("machine-assembly.mmd", bundle.files)
        topology = bundle.files["machine-assembly.mmd"]
        self.assertIn("door: Door", topology)
        self.assertIn("input:DoorInput", topology)
        self.assertIn("notify_safety(event:SafetyInput)", topology)
        self.assertIn("Host effects", topology)
        self.assertIn("write_motor", topology)

    def test_direct_assembly_rust_codegen_raises_without_emitting_fake_rust(self) -> None:
        source = Path("examples/machine_assembly_immediate.glyph").read_text(
            encoding="utf-8"
        )
        model = parse_compilation_model(source)

        with self.assertRaisesRegex(GlyphError, "Rust loweringは未実装"):
            build_rust_artifacts(model)

        analysis = build_analysis_rust_artifacts(model)
        self.assertIn("Rust generation is blocked", analysis.logic)
        self.assertNotIn("compile_error!", analysis.logic)

    def test_plain_tooling_output_has_no_assembly_projection(self) -> None:
        model = parse_compilation_model(PLAIN)
        design = json.loads(build_design_json(model))
        self.assertNotIn("machine_assemblies", design)

        bundle = build_diagram_bundle(model, "plain.glyph")
        self.assertNotIn("machine-assembly-ir.json", bundle.files)
        self.assertNotIn("machine-assembly.mmd", bundle.files)

        actual_rust = build_rust_artifacts(model)
        self.assertNotIn("blocked", actual_rust.logic.lower())
        self.assertNotIn("compile_error!", actual_rust.logic)


if __name__ == "__main__":
    unittest.main()

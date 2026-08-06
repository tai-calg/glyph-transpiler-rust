from __future__ import annotations

import json
from pathlib import Path
import unittest

from glyph import parse_compilation_model
from glyph.compilation import build_design_json, build_diagram_bundle


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
        self.assertEqual(payload["assemblies"][0]["name"], "DoorControl")

        bundle = build_diagram_bundle(model, "machine_assembly_immediate.glyph")
        self.assertIn("machine-assembly-ir.json", bundle.files)
        self.assertIn("machine-assembly.mmd", bundle.files)
        self.assertIn("door: Door", bundle.files["machine-assembly.mmd"])
        self.assertIn("notify_safety", bundle.files["machine-assembly.mmd"])

    def test_plain_tooling_output_uses_original_functions_unchanged(self) -> None:
        model = parse_compilation_model(PLAIN)
        self.assertEqual(
            build_design_json(model),
            build_design_json.__glyph_original__(model),
        )

        actual = build_diagram_bundle(model, "plain.glyph")
        original = build_diagram_bundle.__glyph_original__(model, "plain.glyph")
        self.assertEqual(actual, original)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from glyph import parse_compilation_model
from glyph.artifacts import CompilationModel
from glyph.assembly_frontend import _parse_legacy_compilation_model


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


class MachineAssemblyCompatibilityTests(unittest.TestCase):
    def test_plain_source_uses_original_compilation_model_unchanged(self) -> None:
        model = parse_compilation_model(PLAIN)
        original = _parse_legacy_compilation_model(PLAIN, "input.glyph")

        self.assertIs(type(model), CompilationModel)
        self.assertEqual(model, original)
        self.assertFalse(hasattr(model, "assemblies"))
        self.assertFalse(hasattr(model, "assembly_ir"))
        self.assertFalse(hasattr(model.expanded, "assemblies"))
        self.assertFalse(hasattr(model.expanded, "assembly_ir"))


if __name__ == "__main__":
    unittest.main()

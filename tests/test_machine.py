from __future__ import annotations

import unittest

from glyph import GlyphError, compile_artifacts, parse_artifact_model
from glyph.compiler import FieldExpr, NameExpr


SOURCE = """
+Mode=Idle|Running|Stopped|Faulted
+Command=Stop|Run(U)
+Error=Bad
*Input(tick:B)
*System(mode:Mode,count:U,command:Command)

>step(state:System,input:Input):System|Error
  state.mode==Idle >> Ok(System(Running,state.count+1,Run(1)))
  state.mode==Running >> Ok(System(Stopped,state.count+1,Stop))
  _ >> Ok(state)

machine Controller(state:System,input:Input)
  select=state.mode
  init=System(Idle,0,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted
""".lstrip()


class MachineTests(unittest.TestCase):
    def test_machine_is_extracted_and_validated(self) -> None:
        program, _, _, machines = parse_artifact_model(SOURCE)
        self.assertEqual(len(machines), 1)
        machine = machines[0]
        self.assertEqual(machine.name, "Controller")
        self.assertEqual(machine.state_param.name, "state")
        self.assertIsInstance(machine.selector, FieldExpr)
        self.assertIsInstance(machine.selector.base, NameExpr)
        self.assertGreater(len(program.declarations), 0)

    def test_machine_metadata_does_not_generate_rust_item(self) -> None:
        artifacts = compile_artifacts(SOURCE)
        self.assertNotIn("machine Controller", artifacts.logic)
        self.assertIn("pub fn step", artifacts.logic)

    def test_missing_property_is_rejected(self) -> None:
        source = SOURCE.replace("  failure=Faulted\n", "")
        with self.assertRaisesRegex(GlyphError, "failure"):
            parse_artifact_model(source)

    def test_invalid_selector_is_rejected(self) -> None:
        source = SOURCE.replace("select=state.mode", "select=input.tick")
        with self.assertRaisesRegex(GlyphError, "state.field"):
            parse_artifact_model(source)

    def test_unknown_terminal_variant_is_rejected(self) -> None:
        source = SOURCE.replace("success=Stopped", "success=Missing")
        with self.assertRaisesRegex(GlyphError, "存在しない"):
            parse_artifact_model(source)


if __name__ == "__main__":
    unittest.main()

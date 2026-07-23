from __future__ import annotations

from pathlib import Path
import re
import unittest

from glyph import compile_artifacts, parse_compilation_model


HEADER_FIRST = """system MotorSafety
  sensor -> decide
  decide -> step
  step -> write_motor

machine Motor(state:MotorState,input:Input)
  select=state.mode
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted

+Mode=Stopped|Running|Faulted
+Command=Stop|Drive(U)
*Input(raw:U)
*MotorState(mode:Mode,command:Command)
*Receipt(command:Command)

>decide(input:Input):Command
  input.raw==0 >> Stop
  _ >> Drive(input.raw)

>step(state:MotorState,input:Input):MotorState
  command := decide(input)
  next :=
    command==Stop >> MotorState(Stopped,Stop)
    command==Drive(speed) >> MotorState(Running,Drive(speed))
    _ >> MotorState(Faulted,Stop)
  next

!write_motor(command:Command):Receipt
"""

LEGACY_TAIL = """+Mode=Stopped|Running|Faulted
+Command=Stop|Drive(U)
*Input(raw:U)
*MotorState(mode:Mode,command:Command)
*Receipt(command:Command)

>decide(input:Input):Command
  input.raw==0 >> Stop
  _ >> Drive(input.raw)

>step(state:MotorState,input:Input):MotorState
  command := decide(input)
  next :=
    command==Stop >> MotorState(Stopped,Stop)
    command==Drive(speed) >> MotorState(Running,Drive(speed))
    _ >> MotorState(Faulted,Stop)
  next

!write_motor(command:Command):Receipt

system MotorSafety
  sensor -> decide
  decide -> step
  step -> write_motor

machine Motor(state:MotorState,input:Input)
  select=state.mode
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted
"""


class HeaderFirstLayoutTests(unittest.TestCase):
    def test_system_and_machine_headers_forward_bind(self) -> None:
        model = parse_compilation_model(HEADER_FIRST, "motor.glyph")
        self.assertEqual([system.name for system in model.systems], ["MotorSafety"])
        self.assertEqual([machine.name for machine in model.machines], ["Motor"])
        components = {
            component.name: component.kind
            for component in model.architecture.systems[0].components
        }
        self.assertEqual(components["sensor"], "external")
        self.assertEqual(components["decide"], "function")
        self.assertEqual(components["step"], "function")
        self.assertEqual(components["write_motor"], "effect")

    def test_legacy_tail_placement_remains_compatible(self) -> None:
        header = compile_artifacts(HEADER_FIRST)
        legacy = compile_artifacts(LEGACY_TAIL)
        normalize = lambda value: re.sub(
            r"__glyph_([A-Za-z]+)_L?\d+_",
            r"__glyph_\1_LINE_",
            value,
        )
        self.assertEqual(normalize(header.logic), normalize(legacy.logic))
        self.assertEqual(header.host, legacy.host)

    def test_official_examples_keep_headers_before_body(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for path in sorted((root / "examples").rglob("*.glyph")):
            lines = path.read_text(encoding="utf-8").splitlines()
            body_seen = False
            for line_no, original in enumerate(lines, start=1):
                clean = original.split("#", 1)[0].rstrip()
                if not clean or original[:1].isspace():
                    continue
                if clean.startswith(("system ", "machine ")):
                    self.assertFalse(
                        body_seen,
                        f"{path}:{line_no}: design header must precede declarations",
                    )
                elif not clean.startswith("@"):
                    body_seen = True

    def test_repository_root_contains_only_readme_markdown(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(
            {path.name for path in root.glob("*.md")},
            {"README.md"},
        )
        self.assertTrue((root / "docs" / "README.md").is_file())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import re
import unittest

from glyph import compile_artifacts, parse_compilation_model


SYSTEM_HEADER = """system MotorSafety
  entry cycle
  source sensor
  sink write_motor
"""

MACHINE_HEADER = """machine Motor(state:MotorState,input:Input)
  select=state.mode
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted
"""

BODY = """+Mode=Stopped|Running|Faulted
+Command=Stop|Drive(U)
*Input(raw:U)
*MotorState(mode:Mode,command:Command)
*Receipt(command:Command)

ext sensor():Input

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
>cycle(state:MotorState):Receipt=write_motor(step(state,sensor()).command)
"""

HEADER_FIRST = SYSTEM_HEADER + "\n" + MACHINE_HEADER + "\n" + BODY
TAIL_PLACEMENT = BODY + "\n" + SYSTEM_HEADER + "\n" + MACHINE_HEADER


class HeaderFirstLayoutTests(unittest.TestCase):
    def test_system_and_machine_headers_forward_bind(self) -> None:
        model = parse_compilation_model(HEADER_FIRST, "motor.glyph")
        self.assertEqual([system.name for system in model.systems], ["MotorSafety"])
        self.assertEqual([machine.name for machine in model.machines], ["Motor"])
        system = model.architecture.systems[0]
        components = {
            component.name: (component.kind, component.role)
            for component in system.components
        }
        self.assertEqual(components["sensor"], ("external", "source"))
        self.assertEqual(components["cycle"], ("function", "entry"))
        self.assertEqual(components["write_motor"], ("effect", "sink"))
        self.assertEqual(components["step"], ("function", "internal"))
        self.assertEqual(components["decide"], ("function", "internal"))
        self.assertEqual(system.ports, ())

        names = {component.id: component.name for component in system.components}
        edges = {
            (names[edge.source_id], names[edge.target_id], edge.kind)
            for edge in system.edges
        }
        self.assertEqual(
            edges,
            {
                ("cycle", "write_motor", "call"),
                ("cycle", "step", "call"),
                ("cycle", "sensor", "call"),
                ("step", "decide", "call"),
            },
        )

    def test_tail_placement_remains_compatible(self) -> None:
        header = compile_artifacts(HEADER_FIRST)
        tail = compile_artifacts(TAIL_PLACEMENT)
        normalize = lambda value: re.sub(
            r"__glyph_([A-Za-z]+)_L?\d+_",
            r"__glyph_\1_LINE_",
            value,
        )
        self.assertEqual(normalize(header.logic), normalize(tail.logic))
        self.assertEqual(header.host, tail.host)

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

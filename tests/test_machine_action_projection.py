from __future__ import annotations

import unittest

from glyph.compiler import GlyphError, parse_program
from glyph.machine import extract_machines, validate_machines


VALID = """\
machine Door(state:DoorState,input:Input)
  select=state.mode
  action=state.action
  init=DoorState(Locked,KeepLocked)
  next=step(state,input)
  success=Unlocked
  failure=Faulted

+Input=OpenRequest|NoRequest
+Mode=Locked|Unlocked|Faulted
+Action=KeepLocked|Unlock
*DoorState(mode:Mode,action:Action)

>step(state:DoorState,input:Input):DoorState=DoorState(Unlocked,Unlock)
"""


class MachineActionProjectionTests(unittest.TestCase):
    def compile_machine(self, source: str):
        remainder, machines = extract_machines(source)
        program = parse_program(remainder)
        validate_machines(program, machines)
        self.assertEqual(len(machines), 1)
        return machines[0]

    def test_action_projection_is_optional_and_typed(self) -> None:
        machine = self.compile_machine(VALID)
        self.assertIsNotNone(machine.action_selector)
        self.assertEqual(machine.action_selector.field, "action")

        legacy = VALID.replace("  action=state.action\n", "")
        legacy_machine = self.compile_machine(legacy)
        self.assertIsNone(legacy_machine.action_selector)

    def test_action_and_select_cannot_share_a_field(self) -> None:
        source = VALID.replace("action=state.action", "action=state.mode")
        remainder, machines = extract_machines(source)
        with self.assertRaisesRegex(GlyphError, "actionとselectは同じfield"):
            validate_machines(parse_program(remainder), machines)

    def test_action_projection_must_target_a_sum_typed_state_field(self) -> None:
        source = (
            VALID.replace("action=state.action", "action=state.count")
            .replace(
                "*DoorState(mode:Mode,action:Action)",
                "*DoorState(mode:Mode,action:Action,count:U)",
            )
            .replace(
                "DoorState(Locked,KeepLocked)",
                "DoorState(Locked,KeepLocked,0)",
            )
            .replace(
                "DoorState(Unlocked,Unlock)",
                "DoorState(Unlocked,Unlock,0)",
            )
        )
        remainder, machines = extract_machines(source)
        with self.assertRaisesRegex(GlyphError, "直和型でなければならない"):
            validate_machines(parse_program(remainder), machines)


if __name__ == "__main__":
    unittest.main()

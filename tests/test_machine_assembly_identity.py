from __future__ import annotations

from pathlib import Path
import unittest

from glyph import parse_compilation_model
from glyph.transition_analysis.program_identity import build_program_identity


class MachineAssemblyIdentityTests(unittest.TestCase):
    def test_route_only_change_invalidates_program_identity(self) -> None:
        base = Path("examples/machine_assembly_immediate.glyph").read_text(
            encoding="utf-8"
        )
        first = base.replace(
            "  safety=Safety\n  motor=Motor",
            "  safety=Safety\n  backup=Safety\n  motor=Motor",
        )
        second = first.replace(
            "door.notify_safety -> safety.input",
            "door.notify_safety -> backup.input",
        )

        first_model = parse_compilation_model(first)
        second_model = parse_compilation_model(second)
        first_identity = build_program_identity(
            first_model,
            source_id="assembly.glyph",
            system="DoorControl",
            entry="missing",
        )
        second_identity = build_program_identity(
            second_model,
            source_id="assembly.glyph",
            system="DoorControl",
            entry="missing",
        )

        self.assertEqual(
            first_identity.machine_relation_sha256,
            second_identity.machine_relation_sha256,
        )
        self.assertEqual(
            first_identity.effect_declaration_sha256,
            second_identity.effect_declaration_sha256,
        )
        self.assertNotEqual(
            first_identity.assembly_topology_sha256,
            second_identity.assembly_topology_sha256,
        )
        self.assertNotEqual(
            first_identity.artifact_sha256,
            second_identity.artifact_sha256,
        )
        self.assertNotEqual(first_identity.fingerprint, second_identity.fingerprint)


if __name__ == "__main__":
    unittest.main()

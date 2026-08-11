from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

import glyph.artifacts as artifacts_module
import glyph.compilation as compilation_module
from glyph import IncrementalCompiler, parse_compilation_model
from glyph.assembly_frontend import _reachable_action_effects
from glyph.assembly_runtime import EffectInvocation, ImmediateAssemblyRuntime
from glyph.compiler import FunctionDecl, GlyphError


SOURCE = Path("examples/machine_assembly_immediate.glyph").read_text(encoding="utf-8")
INITIAL = {
    "door": {"mode": "DoorLocked"},
    "safety": {"mode": "SafetyNormal"},
    "motor": {"mode": "MotorRunning"},
}


class MachineAssemblyHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = parse_compilation_model(SOURCE)
        cls.ir = cls.model.assembly_ir[0]

    def test_host_callback_cannot_reenter_same_runtime(self) -> None:
        runtime = ImmediateAssemblyRuntime(self.ir, INITIAL)

        def handler(instance: str, input_name: str, value: object, state: object):
            yield EffectInvocation("write_motor", "DisableMotor")
            return {"mode": "MotorStopped"}

        def host(instance: str, effect: str, arguments: tuple[object, ...]):
            runtime.react("motor", "input", "StopRequested", handler, host)
            return {"command": "DisableMotor"}

        with self.assertRaisesRegex(GlyphError, "top-level反応の再入は禁止"):
            runtime.react("motor", "input", "StopRequested", handler, host)
        self.assertEqual(runtime.states, INITIAL)

    def test_runtime_rejects_unknown_ir_contract(self) -> None:
        with self.assertRaisesRegex(GlyphError, "未対応のAssembly IR契約"):
            ImmediateAssemblyRuntime(replace(self.ir, version=3), INITIAL)
        with self.assertRaisesRegex(GlyphError, "未対応のAssembly IR契約"):
            ImmediateAssemblyRuntime(replace(self.ir, delivery="queued"), INITIAL)

    def test_ir_records_are_not_dict_subclasses(self) -> None:
        record = self.ir.instances[0]
        self.assertNotIsInstance(record, dict)
        with self.assertRaises(TypeError):
            dict.__setitem__(record, "machine", "Other")
        self.assertEqual(record["machine"], "Door")

    def test_empty_normalized_reachability_does_not_fallback(self) -> None:
        machine = next(item for item in self.model.machines if item.name == "Door")
        normalized_lines = {
            clause.line
            for item in self.model.program.declarations
            if isinstance(item, FunctionDecl)
            for clause in item.guards
        }
        self.assertEqual(
            _reachable_action_effects(
                machine,
                self.model,
                set(),
                normalized_lines,
            ),
            set(),
        )

    def test_incremental_cache_includes_name_and_href(self) -> None:
        compiler = IncrementalCompiler()
        first = compiler.compile_text(SOURCE, "a.glyph", "../a.glyph")
        second = compiler.compile_text(SOURCE, "b.glyph", "../b.glyph")
        self.assertTrue(second.changed)
        self.assertIsNot(first.snapshot, second.snapshot)
        self.assertNotEqual(
            first.snapshot.diagrams.files["source-map.json"],
            second.snapshot.diagrams.files["source-map.json"],
        )

    def test_entrypoints_are_owned_without_import_time_rebinding(self) -> None:
        self.assertEqual(
            artifacts_module.parse_compilation_model.__module__,
            "glyph.artifacts",
        )
        self.assertEqual(
            compilation_module.build_design_json.__module__,
            "glyph.compilation",
        )
        self.assertFalse(
            hasattr(compilation_module.build_design_json, "__glyph_original__")
        )


if __name__ == "__main__":
    unittest.main()

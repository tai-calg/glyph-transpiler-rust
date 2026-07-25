from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from glyph import compile_outputs


SOURCE = """
resource Token[Ready]
+Mode=Idle|Running|Failed
+Event=Start|Stop
+Error=Rejected
*State(mode:Mode)

>step(state:State,event:Event):State|Error
  state.mode==Idle >> Ok(State(Running))
  event==Stop >> Err(Rejected)
  _ >> Ok(state)

machine Controller(state:State,event:Event)
  select=state.mode
  init=State(Idle)
  next=step(state,event)
  success=Running
  failure=Failed
""".lstrip()


UNREACHABLE_SOURCE = """
resource Token[Ready]
+Mode=Idle|Running
+Event=Start|Stop
*State(mode:Mode)

>step(state:State,event:Event):State
  state.mode==Idle >> State(Running)
  state.mode==Idle >> State(Idle)
  _ >> state

machine Controller(state:State,event:Event)
  select=state.mode
  init=State(Idle)
  next=step(state,event)
  success=Running
  failure=Idle
""".lstrip()


INTEGER_SOURCE = """
resource Token[Ready]
+Mode=Idle|Running
+Error=Rejected
*State(mode:Mode)

>step(state:State,value:u8):State|Error
  value<10 >> Err(Rejected)
  _ >> Ok(state)

machine Controller(state:State,value:u8)
  select=state.mode
  init=State(Idle)
  next=step(state,value)
  success=Running
  failure=Idle
""".lstrip()


SCENARIO_SOURCE = """
resource Token[Ready]
+Mode=Idle|Running|Stopped|Failed
+Event=Start|Finish|Hold
+Error=Rejected
*State(mode:Mode)

>step(state:State,event:Event):State|Error
  state.mode==Idle >> Ok(State(Running))
  event==Finish >> Ok(State(Stopped))
  _ >> Ok(state)

machine Controller(state:State,event:Event)
  select=state.mode
  init=State(Idle)
  next=step(state,event)
  success=Stopped
  failure=Failed
""".lstrip()


def _compile_and_run_generated(
    source: str,
    source_name: str,
    exports: str,
    artifact_name: str,
    module_name: str,
) -> tuple[object, dict[str, object]]:
    outputs = compile_outputs(source, source_name)
    payload = json.loads(outputs.diagrams.files["type-algebra-tooling.json"])
    with tempfile.TemporaryDirectory(prefix="glyph-machine-generated-") as directory:
        root = Path(directory)
        (root / artifact_name).write_text(
            outputs.diagrams.files[artifact_name],
            encoding="utf-8",
        )
        crate_source = (
            outputs.artifacts.logic
            + f"\npub mod generated {{ pub use super::{{{exports}}}; }}\n"
            + f'pub mod {module_name} {{ include!("{artifact_name}"); }}\n'
        )
        (root / "lib.rs").write_text(crate_source, encoding="utf-8")
        executable = root / "generated-tests"
        compile_result = subprocess.run(
            [
                "rustc",
                "--edition",
                "2021",
                "--test",
                "lib.rs",
                "-o",
                str(executable),
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if compile_result.returncode != 0:
            raise AssertionError(compile_result.stderr)
        run_result = subprocess.run(
            [str(executable)],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if run_result.returncode != 0:
            raise AssertionError(run_result.stdout + run_result.stderr)
    return outputs, payload


def _compile_and_run_witnesses(
    source: str,
    source_name: str,
    exports: str,
) -> tuple[object, dict[str, object]]:
    return _compile_and_run_generated(
        source,
        source_name,
        exports,
        "machine-coverage.generated.rs",
        "machine_coverage",
    )


class TypeAlgebraDeliveryTests(unittest.TestCase):
    def test_normal_compilation_emits_tooling_defaults_and_witnesses(self) -> None:
        outputs = compile_outputs(SOURCE, "delivery.glyph")
        files = outputs.diagrams.files
        self.assertIn("type-algebra-tooling.json", files)
        self.assertIn("machine-coverage.generated.rs", files)
        self.assertIn("machine-scenarios.generated.rs", files)

        payload = json.loads(files["type-algebra-tooling.json"])
        self.assertEqual(payload["schema"], "glyph.type-algebra-tooling")
        self.assertEqual(payload["version"], 2)
        diagnostics = {item["code"] for item in payload["diagnostics"]}
        self.assertNotIn("machine-coverage-fallthrough", diagnostics)
        coverage = payload["machine_coverage"][0]
        self.assertEqual(coverage["fallthrough_pairs"], 2)
        witnesses = payload["machine_witnesses"][0]
        self.assertEqual(witnesses["machine"], "Controller")
        self.assertEqual(witnesses["generated_tests"], 6)
        self.assertEqual(witnesses["skipped_cases"], 0)
        self.assertIn("machine_scenarios", payload)

    def test_normal_compilation_warns_for_unreachable_guard(self) -> None:
        outputs = compile_outputs(UNREACHABLE_SOURCE, "unreachable.glyph")
        payload = json.loads(outputs.diagrams.files["type-algebra-tooling.json"])
        diagnostics = payload["diagnostics"]
        unreachable = [
            item
            for item in diagnostics
            if item["code"] == "machine-coverage-unreachable"
        ]
        self.assertEqual(len(unreachable), 1)
        self.assertIn("ガード#2", unreachable[0]["message"])
        self.assertNotIn(
            "machine-coverage-fallthrough",
            {item["code"] for item in diagnostics},
        )

    def test_generated_machine_witnesses_compile_and_run(self) -> None:
        _, payload = _compile_and_run_witnesses(
            SOURCE,
            "witness.glyph",
            "Mode, Event, Error, State, step, Token",
        )
        witnesses = payload["machine_witnesses"][0]
        self.assertEqual(witnesses["generated_tests"], 6)
        self.assertEqual(witnesses["skipped_cases"], 0)

    def test_partitioned_integer_witnesses_compile_and_run(self) -> None:
        outputs, payload = _compile_and_run_witnesses(
            INTEGER_SOURCE,
            "integer-witness.glyph",
            "Mode, Error, State, step, Token",
        )
        coverage = payload["machine_coverage"][0]
        self.assertTrue(coverage["partitioned"])
        self.assertEqual(coverage["region_count"], 4)
        self.assertEqual(coverage["concrete_case_count"], "512")
        self.assertEqual(
            {item["value"] for case in coverage["cases"] for item in case["regions"]},
            {"0..=9", "10..=255"},
        )
        witnesses = payload["machine_witnesses"][0]
        self.assertEqual(witnesses["generated_tests"], 4)
        self.assertEqual(witnesses["skipped_cases"], 0)
        generated = outputs.diagrams.files["machine-coverage.generated.rs"]
        self.assertIn("step(State { mode: Mode::Idle }, 0)", generated)
        self.assertIn("step(State { mode: Mode::Idle }, 10)", generated)

    def test_multi_step_scenario_compiles_and_replays_shortest_path(self) -> None:
        outputs, payload = _compile_and_run_generated(
            SCENARIO_SOURCE,
            "scenario.glyph",
            "Mode, Event, Error, State, step, Token",
            "machine-scenarios.generated.rs",
            "machine_scenarios",
        )
        report = payload["machine_scenarios"][0]
        self.assertEqual(report["machine"], "Controller")
        self.assertEqual(report["generated_tests"], 2)
        self.assertEqual(report["skipped_targets"], 0)
        self.assertEqual(report["max_steps"], 2)
        stopped = next(
            item for item in report["scenarios"] if item["target_state"] == "Stopped"
        )
        self.assertTrue(stopped["generated"])
        self.assertEqual(stopped["steps"], 2)
        self.assertEqual(len(stopped["case_indices"]), 2)
        generated = outputs.diagrams.files["machine-scenarios.generated.rs"]
        self.assertIn("fn scenario_controller_to_stopped()", generated)
        self.assertIn("step(state, Event::Start)", generated)
        self.assertIn("step(state, Event::Finish)", generated)

    def test_legacy_compilation_emits_empty_machine_tooling_contract(self) -> None:
        outputs = compile_outputs(
            "+Bit=Off|On\n*Pair(left:Bit,right:Bit)\n",
            "legacy-delivery.glyph",
        )
        files = outputs.diagrams.files
        for name in (
            "type-algebra-ir.json",
            "type-algebra-tooling.json",
            "type-algebra.generated.rs",
            "machine-coverage.generated.rs",
            "machine-scenarios.generated.rs",
        ):
            self.assertIn(name, files)
        payload = json.loads(files["type-algebra-tooling.json"])
        self.assertEqual(payload["version"], 2)
        self.assertEqual(payload["machine_coverage"], [])
        self.assertEqual(payload["machine_state_reachability"], [])
        self.assertEqual(payload["machine_witnesses"], [])
        self.assertEqual(payload["machine_scenarios"], [])
        self.assertIn(
            "No executable witness tests were safe to generate",
            files["machine-coverage.generated.rs"],
        )
        self.assertIn(
            "No executable multi-step scenarios were safe to generate",
            files["machine-scenarios.generated.rs"],
        )


if __name__ == "__main__":
    unittest.main()

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


class TypeAlgebraDeliveryTests(unittest.TestCase):
    def test_normal_compilation_emits_tooling_fallthrough_and_witnesses(self) -> None:
        outputs = compile_outputs(SOURCE, "delivery.glyph")
        files = outputs.diagrams.files
        self.assertIn("type-algebra-tooling.json", files)
        self.assertIn("machine-coverage.generated.rs", files)

        payload = json.loads(files["type-algebra-tooling.json"])
        diagnostics = {item["code"] for item in payload["diagnostics"]}
        self.assertIn("machine-coverage-fallthrough", diagnostics)
        coverage = payload["machine_coverage"][0]
        self.assertEqual(coverage["fallthrough_pairs"], 2)
        witnesses = payload["machine_witnesses"][0]
        self.assertEqual(witnesses["machine"], "Controller")
        self.assertEqual(witnesses["generated_tests"], 6)
        self.assertEqual(witnesses["skipped_cases"], 0)

    def test_generated_machine_witnesses_compile_and_run(self) -> None:
        outputs = compile_outputs(SOURCE, "witness.glyph")
        with tempfile.TemporaryDirectory(prefix="glyph-machine-witness-") as directory:
            root = Path(directory)
            (root / "machine-coverage.generated.rs").write_text(
                outputs.diagrams.files["machine-coverage.generated.rs"],
                encoding="utf-8",
            )
            crate_source = (
                outputs.artifacts.logic
                + "\npub mod generated { pub use super::{Mode, Event, Error, State, step, Token}; }\n"
                + "pub mod machine_coverage { include!(\"machine-coverage.generated.rs\"); }\n"
            )
            (root / "lib.rs").write_text(crate_source, encoding="utf-8")
            executable = root / "machine-coverage-tests"
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
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run_result = subprocess.run(
                [str(executable)],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                run_result.returncode,
                0,
                run_result.stdout + run_result.stderr,
            )

    def test_legacy_compilation_does_not_gain_type_algebra_artifacts(self) -> None:
        outputs = compile_outputs(
            "+Bit=Off|On\n*Pair(left:Bit,right:Bit)\n",
            "legacy-delivery.glyph",
        )
        self.assertNotIn("type-algebra-tooling.json", outputs.diagrams.files)
        self.assertNotIn("machine-coverage.generated.rs", outputs.diagrams.files)


if __name__ == "__main__":
    unittest.main()

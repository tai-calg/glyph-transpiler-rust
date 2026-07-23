from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from glyph.compilation import CompilationPipeline
from glyph.diagram_app import GlyphDiagramApp
from glyph.diagram_ui import DIAGRAM_HTML
from glyph.io_state_views import build_io_state_views


MOTOR_SOURCE = """\
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

@MAX=100
@STOP_LIMIT=100ms

*Input(raw:F,enabled,emergency,fault,stopped:B)
+Command=Stop|Drive(F)
+Mode=Stopped|Running|Faulted
*MotorState(mode:Mode,command:Command)
*Receipt(command:Command)

?emergency_stop(*Input)=@A(emergency >> @E STOP_LIMIT stopped)
?fault_stop(*Input)=@A(fault >> @E STOP_LIMIT stopped)

>decide(input:Input):Command
  normalized :=
    input.raw
    /> |x| min(x,1.0)

  command :=
    input.emergency|input.fault >> Stop
    !input.enabled >> Stop
    _ >> Drive(normalized)

  command

>step(state:MotorState,input:Input):MotorState
  command := decide(input)
  next :=
    command==Stop >> MotorState(Stopped,Stop)
    command==Drive(speed) >> MotorState(Running,Drive(speed))
    _ >> MotorState(Faulted,Stop)
  next

!write_motor(command:Command):Receipt
"""


EXPLICIT_STATE_SOURCE = """\
machine Controller(state:State,input:Input)
  select=state.mode
  init=State(Idle)
  next=step(state,input)
  success=Idle
  failure=Faulted

+Mode=Idle|Running|Faulted
*State(mode:Mode)
*Input(start:B,stop:B,fault:B)

>step(state:State,input:Input):State
  state.mode==Idle&input.start >> State(Running)
  state.mode==Running&input.stop >> State(Idle)
  input.fault >> State(Faulted)
  state.mode==Faulted >> State(Faulted)
  _ >> state
"""


class IoStateViewsTests(unittest.TestCase):
    def compile_views(self, source: str) -> dict[str, object]:
        output = CompilationPipeline().compile_text(source, source_name="test.glyph")
        return build_io_state_views(output.model, output.diagrams.ir)

    def test_declared_system_projects_typed_component_ports(self) -> None:
        views = self.compile_views(MOTOR_SOURCE)
        self.assertEqual(views["schema"], "glyph.io-state-views")
        self.assertEqual(views["version"], 2)
        systems = views["io"]["systems"]
        motor = next(item for item in systems if item["name"] == "MotorSafety")
        nodes = {item["name"]: item for item in motor["nodes"]}

        self.assertFalse(nodes["sensor"]["declared_io"])
        self.assertEqual(
            nodes["decide"]["inputs"],
            [{"name": "input", "type": "Input"}],
        )
        self.assertEqual(nodes["decide"]["output"], "Command")
        self.assertEqual(nodes["step"]["output"], "MotorState")
        self.assertEqual(nodes["write_motor"]["kind"], "effect")
        self.assertEqual(nodes["write_motor"]["output"], "Receipt")
        self.assertEqual(len(motor["edges"]), 3)

    def test_machine_normalization_expands_wildcards_and_reports_dead_logic(self) -> None:
        views = self.compile_views(MOTOR_SOURCE)
        machines = views["state"]["machines"]
        self.assertEqual(len(machines), 1)
        machine = machines[0]
        self.assertEqual(machine["name"], "Motor")
        self.assertEqual(machine["initial_state"], "Stopped")
        self.assertEqual(
            {state["name"] for state in machine["states"]},
            {"Stopped", "Running", "Faulted"},
        )

        transitions = machine["transitions"]
        self.assertEqual(len(transitions), 6)
        self.assertFalse(
            any(
                transition["source_state"] == "*"
                or transition["target_state"] == "*"
                for transition in transitions
            )
        )
        self.assertEqual(
            {
                (transition["source_state"], transition["target_state"])
                for transition in transitions
            },
            {
                ("Stopped", "Stopped"),
                ("Stopped", "Running"),
                ("Running", "Stopped"),
                ("Running", "Running"),
                ("Faulted", "Stopped"),
                ("Faulted", "Running"),
            },
        )
        self.assertEqual(machine["unreachable_states"], ["Faulted"])
        state_by_name = {state["name"]: state for state in machine["states"]}
        self.assertTrue(state_by_name["Stopped"]["reachable"])
        self.assertTrue(state_by_name["Running"]["reachable"])
        self.assertFalse(state_by_name["Faulted"]["reachable"])
        codes = {item["code"] for item in machine["diagnostics"]}
        self.assertEqual(
            codes,
            {
                "unreachable-branch",
                "unreachable-state",
                "state-independent-transition",
            },
        )
        self.assertEqual(machine["analysis"]["raw_transition_count"], 3)
        self.assertEqual(machine["analysis"]["normalized_transition_count"], 6)
        self.assertEqual(machine["analysis"]["reachable_state_count"], 2)

    def test_explicit_state_conditions_remain_concrete(self) -> None:
        views = self.compile_views(EXPLICIT_STATE_SOURCE)
        machine = views["state"]["machines"][0]
        self.assertFalse(
            any(
                transition["source_state"] == "*"
                or transition["target_state"] == "*"
                for transition in machine["transitions"]
            )
        )
        self.assertIn(
            ("Idle", "Running"),
            {
                (transition["source_state"], transition["target_state"])
                for transition in machine["transitions"]
            },
        )
        self.assertEqual(machine["unreachable_states"], [])
        self.assertNotIn(
            "state-independent-transition",
            {item["code"] for item in machine["diagnostics"]},
        )

    def test_source_without_system_uses_generic_call_graph(self) -> None:
        views = self.compile_views(
            """
>inc(x:U):U=x+1
>twice(x:U):U=inc(inc(x))
"""
        )
        systems = views["io"]["systems"]
        self.assertEqual(len(systems), 1)
        self.assertEqual(systems[0]["kind"], "derived-call-graph")
        self.assertEqual(
            {node["name"] for node in systems[0]["nodes"]},
            {"inc", "twice"},
        )
        self.assertIn(
            ("fn_twice", "fn_inc"),
            {
                (edge["source_id"], edge["target_id"])
                for edge in systems[0]["edges"]
            },
        )

    def test_state_is_not_inferred_without_machine_declaration(self) -> None:
        views = self.compile_views(">inc(x:U):U=x+1\n")
        self.assertEqual(views["state"]["machines"], [])


class GlyphDiagramAppTests(unittest.TestCase):
    def test_rebuild_exposes_views_and_writes_json_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "motor.glyph"
            source.write_text(MOTOR_SOURCE, encoding="utf-8")
            app = GlyphDiagramApp(source)
            snapshot = app.rebuild()

            self.assertEqual(snapshot.status, "ready")
            self.assertEqual(snapshot.views["summary"]["machines"], 1)
            self.assertEqual(snapshot.views["summary"]["state_warnings"], 3)
            self.assertTrue(app.output_path.is_file())
            saved = json.loads(app.output_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["schema"], "glyph.io-state-views")
            self.assertEqual(saved["version"], 2)

    def test_http_state_serves_compiler_derived_views(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "motor.glyph"
            source.write_text(MOTOR_SOURCE, encoding="utf-8")
            app = GlyphDiagramApp(source)
            app.rebuild()
            server = app.create_server()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            try:
                with urlopen(f"http://{host}:{port}/api/state") as response:
                    state = json.loads(response.read().decode("utf-8"))
                self.assertEqual(state["status"], "ready")
                self.assertEqual(state["views"]["schema"], "glyph.io-state-views")
                self.assertEqual(state["views"]["version"], 2)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1.0)

    def test_frontend_renders_only_concrete_states_and_static_diagnostics(self) -> None:
        for marker in (
            "Glyph Diagram",
            "I/O topology",
            "State transitions",
            "renderIoGraph",
            "renderStateGraph",
            "renderMachineDiagnostics",
            "unreachable state",
            "ワイルドカードは実状態へ展開",
            "/api/preview",
            "/api/save",
            "machine宣言がないため、状態遷移は推測しない",
        ):
            self.assertIn(marker, DIAGRAM_HTML)
        self.assertNotIn("Any state", DIAGRAM_HTML)
        self.assertNotIn("needsAny", DIAGRAM_HTML)
        self.assertNotIn("gradio", DIAGRAM_HTML.lower())

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_frontend_javascript_is_syntactically_valid(self) -> None:
        match = re.search(r"<script>(.*)</script>", DIAGRAM_HTML, re.DOTALL)
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "diagram.js"
            script.write_text(match.group(1), encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(script)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

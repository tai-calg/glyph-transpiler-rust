from __future__ import annotations

from http import HTTPStatus
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from glyph.desktop_server import create_desktop_server
from glyph.transition_analysis import (
    VerifiedEffectContractRegistry,
    build_strict_io_state_views,
    read_only_identity_contract,
)


SOURCE = """machine Counter(state:State,input:Input)
  select=state.mode
  init=State(Idle)
  next=step(state,input)
  success=Running
  failure=Faulted

+Mode=Idle|Running|Faulted
*State(mode:Mode)
*Input(start:B,fault:B)

>step(state:State,input:Input):State
  input.fault >> State(Faulted)
  state.mode==Idle&input.start >> State(Running)
  _ >> state
"""

STRICT_SOURCE = """system DoorControl
  entry control

  in state:DoorState
  in input:Input
  out state_out:DoorState

  state -> control
  input -> control
  control -> state_out
  control -> actuator

machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*Input(open_request:B)
+DoorMode=Closed|Open|Alarm
*DoorState(mode:DoorMode)

!actuator(state:DoorState):DoorState

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request >> DoorState(Open)
  _ >> state

>control(state:DoorState,input:Input):DoorState
  next := step(state,input)
  observed := actuator(next)
  observed
"""


class DesktopServerTests(unittest.TestCase):
    def test_launch_bootstraps_header_auth_and_api_rejects_unauthenticated_clients(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "counter.glyph"
            source_path.write_text(SOURCE, encoding="utf-8")
            desktop = create_desktop_server(source_path, token="test-token")
            thread = threading.Thread(target=desktop.server.serve_forever, daemon=True)
            thread.start()
            host, port = desktop.server.server_address[:2]
            api_url = f"http://{host}:{port}/api/state"
            try:
                with self.assertRaises(HTTPError) as rejected:
                    urlopen(api_url, timeout=3)
                self.assertEqual(rejected.exception.code, HTTPStatus.FORBIDDEN)

                launch = urlopen(desktop.launch_url, timeout=3)
                self.assertEqual(launch.status, HTTPStatus.OK)
                html = launch.read().decode("utf-8")
                self.assertIn("X-Glyph-Desktop-Token", html)
                self.assertIn('const token = "test-token"', html)
                cookie = launch.headers.get("Set-Cookie")
                self.assertIsNotNone(cookie)
                assert cookie is not None
                self.assertIn("glyph_desktop_session=test-token", cookie)
                self.assertIn("HttpOnly", cookie)

                request = Request(
                    api_url,
                    headers={"X-Glyph-Desktop-Token": "test-token"},
                )
                state = json.loads(urlopen(request, timeout=3).read().decode("utf-8"))
                self.assertEqual(state["status"], "ready")
                self.assertEqual(Path(state["source_path"]), source_path)
            finally:
                desktop.close()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())

    def test_desktop_server_publishes_strict_native_evidence_without_legacy_analyzer(self) -> None:
        contracts = VerifiedEffectContractRegistry(
            defaults=(
                (
                    "actuator",
                    read_only_identity_contract(
                        "actuator",
                        "state",
                        source="desktop campaign: reviewed identity actuator",
                    ),
                ),
            )
        )

        def strict_views(model: object, execution: object) -> dict[str, object]:
            return build_strict_io_state_views(  # type: ignore[arg-type]
                model,
                execution,
                contracts,
            )

        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "strict-door.glyph"
            source_path.write_text(STRICT_SOURCE, encoding="utf-8")
            desktop = create_desktop_server(
                source_path,
                token="strict-token",
                view_builder=strict_views,
            )
            thread = threading.Thread(target=desktop.server.serve_forever, daemon=True)
            thread.start()
            host, port = desktop.server.server_address[:2]
            api_url = f"http://{host}:{port}/api/state"
            try:
                launch = urlopen(desktop.launch_url, timeout=3)
                html = launch.read().decode("utf-8")
                self.assertIn("glyph-transition-semantic-status-ui-v2", html)
                self.assertIn("function liveState()", html)
                self.assertIn("new AbortController()", html)
                self.assertIn("window.addEventListener(\"pagehide\",dispose", html)
                self.assertIn('const token = "strict-token"', html)

                request = Request(
                    api_url,
                    headers={"X-Glyph-Desktop-Token": "strict-token"},
                )
                state = json.loads(urlopen(request, timeout=3).read().decode("utf-8"))
                self.assertEqual(state["status"], "ready")
                views = state["views"]
                self.assertEqual(views["rtai_projection_mode"], "strict-exact")
                self.assertFalse(views["rtai_legacy_system_action_analyzer_enabled"])
                self.assertTrue(views["strict_projection_campaign"]["ready"])
                self.assertFalse(
                    views["strict_projection_campaign"]["legacy_fallback_allowed"]
                )
                transitions = views["state"]["machines"][0]["transitions"]
                self.assertTrue(transitions)
                for transition in transitions:
                    self.assertEqual(
                        transition["rtai_semantic_status"]["status"],
                        "exact",
                    )
                    self.assertEqual(
                        transition["system_action_projection_source"],
                        "rtai-execution-evidence-v2",
                    )
                    self.assertFalse(
                        transition["legacy_system_action_fallback_allowed"]
                    )
                    self.assertNotIn("execution_evidence_v2", transition)
            finally:
                desktop.close()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())

    def test_desktop_server_is_loopback_only_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "counter.glyph"
            source_path.write_text(SOURCE, encoding="utf-8")
            desktop = create_desktop_server(source_path, token="test-token")
            try:
                host, _port = desktop.server.server_address[:2]
                self.assertEqual(host, "127.0.0.1")
            finally:
                desktop.server.server_close()
                desktop.app.stop()


if __name__ == "__main__":
    unittest.main()

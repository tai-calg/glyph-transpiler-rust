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

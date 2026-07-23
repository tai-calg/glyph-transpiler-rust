from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from glyph.studio import GlyphStudio, STUDIO_HTML


class GlyphStudioTests(unittest.TestCase):
    def test_one_rebuild_generates_all_views(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.glyph"
            source.write_text(">inc(x:U):U=x+1\n", encoding="utf-8")
            studio = GlyphStudio(source)
            snapshot = studio.rebuild()
            self.assertEqual(snapshot.status, "ready")
            for name in (
                "generated.rs",
                "host.generated.rs",
                "manual.rs",
                "typed-ast.json",
                "studio-views.json",
                "execution.mmd",
                "execution-ir.json",
                "source-map.json",
                "index.md",
            ):
                self.assertIn(name, snapshot.artifacts)
                self.assertTrue((studio.output_dir / name).exists(), name)

    def test_compile_error_is_visible_without_losing_previous_views(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.glyph"
            source.write_text(">inc(x:U):U=x+1\n", encoding="utf-8")
            studio = GlyphStudio(source)
            ready = studio.rebuild()
            broken = studio.rebuild(">broken(x:U):U=\n")
            self.assertEqual(broken.status, "error")
            self.assertTrue(broken.diagnostics)
            self.assertEqual(broken.artifacts["generated.rs"], ready.artifacts["generated.rs"])
            self.assertEqual(broken.glyph04_views, ready.glyph04_views)

    def test_save_source_updates_file_and_compilation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.glyph"
            source.write_text(">inc(x:U):U=x+1\n", encoding="utf-8")
            studio = GlyphStudio(source)
            studio.rebuild()
            snapshot = studio.save_source(">double(x:U):U=x*2\n")
            self.assertEqual(snapshot.status, "ready")
            self.assertIn("pub fn double", snapshot.artifacts["generated.rs"])
            self.assertIn("double", source.read_text(encoding="utf-8"))

    def test_http_app_serves_state_and_accepts_save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.glyph"
            source.write_text(">inc(x:U):U=x+1\n", encoding="utf-8")
            studio = GlyphStudio(source)
            studio.rebuild()
            server = studio.create_server()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            try:
                with urlopen(f"http://{host}:{port}/api/state") as response:
                    state = json.loads(response.read().decode("utf-8"))
                self.assertEqual(state["status"], "ready")
                self.assertIn("glyph04_views", state)

                payload = json.dumps({"source": ">triple(x:U):U=x*3\n"}).encode("utf-8")
                request = Request(
                    f"http://{host}:{port}/api/save",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request) as response:
                    saved = json.loads(response.read().decode("utf-8"))
                self.assertEqual(saved["status"], "ready")
                self.assertIn("triple", source.read_text(encoding="utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1.0)

    def test_studio_html_contains_integrated_views(self) -> None:
        for label in (
            "Glyph Studio",
            "Capability",
            "Resource",
            "World/Region",
            "Protocol",
            "Handler",
            "Law/Monitor",
            "Verification",
            "Architecture",
            "State",
            "Logic",
            "Flow",
            "Time",
            "Rust",
            "AST",
            "Symbols",
        ):
            self.assertIn(label, STUDIO_HTML)


if __name__ == "__main__":
    unittest.main()

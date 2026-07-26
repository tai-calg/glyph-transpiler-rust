from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

from glyph import compile_outputs


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"


class TauriDesktopTests(unittest.TestCase):
    def test_default_desktop_source_compiles(self) -> None:
        source_path = DESKTOP / "resources" / "default.glyph"
        result = compile_outputs(source_path.read_text(encoding="utf-8"), source_path.name)
        self.assertIn("pub fn control", result.artifacts.logic)
        self.assertIn("architecture-ir.json", result.diagrams.files)

    def test_tauri_security_boundary_is_narrow(self) -> None:
        config = json.loads(
            (DESKTOP / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
        )
        capability = json.loads(
            (DESKTOP / "src-tauri" / "capabilities" / "default.json").read_text(
                encoding="utf-8"
            )
        )
        csp = config["app"]["security"]["csp"]
        self.assertIn("frame-src http://127.0.0.1:*", csp)
        self.assertNotIn("dangerousRemoteDomainIpcAccess", config["app"]["security"])
        self.assertEqual(capability["permissions"], ["core:default"])
        self.assertNotIn("shell:", json.dumps(capability))
        self.assertNotIn("fs:", json.dumps(capability))

    def test_remote_compiler_ui_is_sandboxed(self) -> None:
        html = (DESKTOP / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn('sandbox="allow-scripts allow-same-origin allow-downloads allow-forms"', html)
        self.assertNotIn("allow-top-navigation", html)
        self.assertNotIn("allow-popups", html)

    def test_sidecar_lifecycle_is_owned_by_rust_shell(self) -> None:
        rust = (DESKTOP / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")
        self.assertIn('.sidecar("glyph-studio-server")', rust)
        self.assertIn("child.kill()", rust)
        self.assertIn("ExitRequested", rust)
        self.assertIn("FileDialog::new()", rust)
        self.assertIn("GLYPH_DESKTOP_READY=", rust)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_desktop_javascript_is_syntactically_valid(self) -> None:
        result = subprocess.run(
            ["node", "--check", str(DESKTOP / "ui" / "app.js")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from glyph.ui_manifest import (
    UI_MANIFEST_SCHEMA,
    UiManifestError,
    apply_ui_manifest,
    load_ui_manifest,
    parse_ui_manifest,
)
from glyph.ui_public import RendererRegistry, open_ui_project


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "examples" / "gradio_profile.glyph"
PROFILE_MANIFEST = ROOT / "examples" / "gradio_profile.ui.json"


class PublicUiTests(unittest.TestCase):
    def test_manifest_applies_only_to_semantic_node_ids(self) -> None:
        manifest = load_ui_manifest(PROFILE_MANIFEST)
        with open_ui_project(PROFILE, manifest=manifest) as project:
            app = project.application
            self.assertEqual(app.title, "Profile Access Inspector")
            profile = app.action.inputs[0]
            children = {child.id: child for child in profile.children}
            self.assertEqual(children["input:profile.name"].label, "Display name")
            self.assertEqual(children["input:profile.name"].default, "Ada")
            self.assertEqual(children["input:profile.age"].minimum, 0)
            self.assertEqual(children["input:profile.age"].maximum, 130)
            self.assertTrue(children["input:profile.active"].default)
            result = project.runtime.invoke(
                app.action.name,
                {"profile": {"name": "Ada", "age": 35, "active": True}},
            ).to_python()
        self.assertEqual(result["access"]["variant"], "Admin")

    def test_manifest_rejects_unknown_fields_and_code_like_escape_hatches(self) -> None:
        with self.assertRaisesRegex(UiManifestError, "unknown manifest field"):
            parse_ui_manifest(
                {
                    "schema": UI_MANIFEST_SCHEMA,
                    "version": 1,
                    "python": "os.system('bad')",
                }
            )
        with self.assertRaisesRegex(UiManifestError, "unknown field"):
            parse_ui_manifest(
                {
                    "schema": UI_MANIFEST_SCHEMA,
                    "version": 1,
                    "nodes": {"input:x": {"callback": "module:function"}},
                }
            )

    def test_manifest_rejects_unknown_node_ids(self) -> None:
        manifest = parse_ui_manifest(
            {
                "schema": UI_MANIFEST_SCHEMA,
                "version": 1,
                "nodes": {"input:missing": {"label": "Missing"}},
            }
        )
        with open_ui_project(PROFILE) as project:
            with self.assertRaisesRegex(UiManifestError, "unknown UI node ID"):
                apply_ui_manifest(project.application, manifest)

    def test_renderer_registry_is_public_and_replace_is_explicit(self) -> None:
        registry = RendererRegistry()
        registry.register("test", lambda runtime, app, **options: app.action.name)
        self.assertEqual(registry.names(), ("test",))
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register("test", lambda runtime, app, **options: None)
        registry.register("test", lambda runtime, app, **options: "replaced", replace=True)
        self.assertEqual(registry.get("test")(None, None), "replaced")  # type: ignore[arg-type]

    def test_console_cli_check_uses_manifest_without_importing_gradio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "ui-ir.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "glyph.ui_cli",
                    str(PROFILE),
                    "--manifest",
                    str(PROFILE_MANIFEST),
                    "--check",
                    "--ui-ir-output",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            parsed = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(parsed["schema"], "glyph.ui-ir")
        self.assertEqual(parsed["title"], "Profile Access Inspector")

    def test_project_context_manager_stops_runtime(self) -> None:
        project = open_ui_project(PROFILE)
        project.start_watching(0.1)
        watcher = project.runtime._watcher
        self.assertIsNotNone(watcher)
        project.close()
        self.assertFalse(watcher.is_alive())  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()

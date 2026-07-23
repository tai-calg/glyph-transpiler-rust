from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from glyph.ui import UI_API_VERSION, compile_ui_source, open_ui
from glyph.ui_backends import BACKEND_API_VERSION, BackendRegistry, UiBackendError
from glyph.ui_schema import (
    UI_SCHEMA_API_VERSION,
    UiSchemaError,
    fingerprint_ui_application,
    load_ui_application,
    loads_ui_application,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeBackend:
    name = "fake"
    api_version = BACKEND_API_VERSION

    def build(self, project, **options):
        return {
            "action": project.application.action.name,
            "options": options,
            "fingerprint": project.schema_fingerprint,
        }

    def launch(self, project, **options):
        return self.build(project, **options)


class PublicUiApiTests(unittest.TestCase):
    def test_public_api_versions_are_explicit(self) -> None:
        self.assertEqual(UI_API_VERSION, 1)
        self.assertEqual(UI_SCHEMA_API_VERSION, 1)
        self.assertEqual(BACKEND_API_VERSION, 1)

    def test_compile_and_round_trip_ui_ir(self) -> None:
        source = "*Input(name:S,enabled:B)\n*View(name:S,enabled:B)\n>render(input:Input):View=View(input.name,input.enabled)\n"
        application = compile_ui_source(source, source_name="memory.glyph")
        loaded = loads_ui_application(application.to_json())

        self.assertEqual(loaded.to_dict(), application.to_dict())
        self.assertEqual(
            fingerprint_ui_application(loaded),
            fingerprint_ui_application(application),
        )

    def test_schema_loader_rejects_unknown_version_and_duplicate_ids(self) -> None:
        application = compile_ui_source(">render(x:U):U=x\n")
        document = application.to_dict()
        document["version"] = 99
        with self.assertRaisesRegex(UiSchemaError, "unsupported"):
            load_ui_application(document)

        duplicate = application.to_dict()
        duplicate["action"]["output"]["id"] = duplicate["action"]["inputs"][0]["id"]
        with self.assertRaisesRegex(UiSchemaError, "duplicate"):
            load_ui_application(duplicate)

    def test_custom_backend_uses_only_public_project_contract(self) -> None:
        registry = BackendRegistry()
        registry.register("fake", FakeBackend)
        with open_ui(
            ROOT / "examples" / "gradio_profile.glyph",
            registry=registry,
        ) as project:
            built = project.build("fake", compact=True)
            invoked = project.invoke(
                {"profile": {"name": "Ada", "age": 35, "active": True}},
                refresh=False,
            ).to_python()

        self.assertEqual(built["action"], "render")
        self.assertTrue(built["options"]["compact"])
        self.assertEqual(invoked["access"]["variant"], "Admin")

    def test_duplicate_backend_registration_is_rejected(self) -> None:
        registry = BackendRegistry()
        registry.register("fake", FakeBackend)
        with self.assertRaisesRegex(UiBackendError, "already registered"):
            registry.register("fake", FakeBackend)

    def test_body_change_keeps_component_fingerprint_but_signature_change_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.glyph"
            path.write_text(">render(x:U):U=x+1\n", encoding="utf-8")
            with open_ui(path) as project:
                original = project.schema_fingerprint
                path.write_text("# body-only edit\n>render(x:U):U=x+2\n", encoding="utf-8")
                body = project.inspect_schema(force=True)
                self.assertFalse(body.changed)
                self.assertEqual(project.schema_fingerprint, original)

                path.write_text(">render(x:I):I=x+2\n", encoding="utf-8")
                signature = project.inspect_schema(force=True)
                self.assertTrue(signature.changed)
                self.assertTrue(project.requires_restart)

    def test_importing_public_core_does_not_import_optional_ui_libraries(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import glyph.ui; "
                    "assert 'gradio' not in sys.modules; "
                    "assert 'pandas' not in sys.modules"
                ),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_serialized_schema_is_plain_json(self) -> None:
        application = compile_ui_source(">render(flag:B):B=flag\n")
        payload = json.loads(application.to_json())
        self.assertEqual(payload["schema"], "glyph.ui-ir")
        self.assertEqual(payload["version"], 1)


if __name__ == "__main__":
    unittest.main()

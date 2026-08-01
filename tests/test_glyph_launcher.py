from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from glyph.compilation import CompilationPipeline
from glyph.default_workspace import APPLICATION_IDENTIFIER
from glyph.io_state_views import build_io_state_views
from glyph import launcher


ROOT = Path(__file__).resolve().parents[1]


class GlyphLauncherTests(unittest.TestCase):
    def test_input_argument_is_optional(self) -> None:
        args = launcher.build_parser().parse_args([])
        self.assertIsNone(args.input)

    def test_macos_default_workspace_matches_tauri_application_data(self) -> None:
        home = Path("/Users/example")
        directory = launcher.application_data_directory(
            home=home,
            platform="darwin",
            environ={},
        )
        self.assertEqual(
            directory,
            home / "Library" / "Application Support" / APPLICATION_IDENTIFIER,
        )
        self.assertEqual(
            launcher.default_input_path(directory),
            directory / "workspace.glyph",
        )

    def test_default_workspace_is_created_once_from_canonical_resource(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_directory = Path(directory) / "app-data"
            path = launcher.resolve_input(None, data_directory=data_directory)
            self.assertEqual(path, data_directory / "workspace.glyph")
            self.assertEqual(path.read_text(encoding="utf-8"), launcher.DEFAULT_SOURCE)

            path.write_text("system Custom\n", encoding="utf-8")
            second = launcher.resolve_input(None, data_directory=data_directory)
            self.assertEqual(second, path)
            self.assertEqual(path.read_text(encoding="utf-8"), "system Custom\n")

    def test_canonical_default_source_compiles_into_state_and_io_views(self) -> None:
        output = CompilationPipeline().compile_text(
            launcher.DEFAULT_SOURCE,
            source_name="default-workspace.glyph",
        )
        views = build_io_state_views(output.model, output.diagrams.ir)
        self.assertTrue(views["state"]["machines"])
        self.assertTrue(views["io"]["systems"])
        machine = views["state"]["machines"][0]
        self.assertEqual(machine["name"], "Door")
        self.assertTrue(machine["transitions"])
        self.assertIn("architecture-ir.json", output.diagrams.files)

    def test_unmodified_generated_cli_samples_are_migrated(self) -> None:
        for generated in (
            launcher.LEGACY_DEFAULT_SOURCE,
            launcher.CODE_DERIVED_DEFAULT_SOURCE,
            launcher.PREVIOUS_CLI_DEFAULT_SOURCE,
        ):
            with self.subTest(prefix=generated.splitlines()[0]):
                with tempfile.TemporaryDirectory() as directory:
                    data_directory = Path(directory) / "app-data"
                    path = launcher.default_input_path(data_directory)
                    path.parent.mkdir(parents=True)
                    path.write_text(generated, encoding="utf-8")
                    launcher.resolve_input(None, data_directory=data_directory)
                    self.assertEqual(
                        path.read_text(encoding="utf-8"),
                        launcher.DEFAULT_SOURCE,
                    )

    def test_existing_legacy_cwd_workspace_is_copied_to_shared_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = launcher.legacy_input_path(root)
            legacy.parent.mkdir(parents=True)
            source = "system UserWorkspace\n# preserve this edit\n"
            legacy.write_text(source, encoding="utf-8")
            data_directory = root / "application-data"

            resolved = launcher.resolve_input(
                None,
                data_directory=data_directory,
                legacy_root=root,
            )
            self.assertEqual(resolved, data_directory / "workspace.glyph")
            self.assertEqual(resolved.read_text(encoding="utf-8"), source)
            self.assertEqual(legacy.read_text(encoding="utf-8"), source)

    def test_explicit_input_is_preserved(self) -> None:
        explicit = Path("examples/state_diagrams/traffic_light.glyph")
        self.assertEqual(launcher.resolve_input(explicit), explicit)

    def test_main_starts_the_shared_authenticated_studio_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "workspace.glyph"
            source.write_text(launcher.DEFAULT_SOURCE, encoding="utf-8")
            with patch.object(launcher, "run_studio_app", return_value=0) as run:
                self.assertEqual(launcher.main([str(source)]), 0)
                run.assert_called_once_with(source)

    def test_root_python_entrypoint_is_only_a_package_launcher_wrapper(self) -> None:
        wrapper = (ROOT / "glyph.py").read_text(encoding="utf-8")
        self.assertIn("from glyph.launcher import main", wrapper)
        self.assertNotIn("DEFAULT_SOURCE", wrapper)
        self.assertNotIn("run_diagram_app", wrapper)


if __name__ == "__main__":
    unittest.main()

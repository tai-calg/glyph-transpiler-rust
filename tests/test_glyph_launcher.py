from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("glyph_launcher", ROOT / "glyph.py")
assert SPEC is not None and SPEC.loader is not None
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class GlyphLauncherTests(unittest.TestCase):
    def test_input_argument_is_optional(self) -> None:
        args = launcher.build_parser().parse_args([])
        self.assertIsNone(args.input)

    def test_default_workspace_is_created_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = launcher.default_input_path(root)
            with patch.object(launcher.Path, "cwd", return_value=root):
                resolved = launcher.resolve_input(None)
                self.assertEqual(resolved, path)
                self.assertEqual(path.read_text(encoding="utf-8"), launcher.DEFAULT_SOURCE)

                path.write_text("system Custom\n", encoding="utf-8")
                second = launcher.resolve_input(None)
                self.assertEqual(second, path)
                self.assertEqual(path.read_text(encoding="utf-8"), "system Custom\n")

    def test_untouched_legacy_default_is_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = launcher.default_input_path(root)
            path.parent.mkdir(parents=True)
            path.write_text(launcher.LEGACY_DEFAULT_SOURCE, encoding="utf-8")

            with patch.object(launcher.Path, "cwd", return_value=root):
                self.assertEqual(launcher.resolve_input(None), path)

            self.assertEqual(path.read_text(encoding="utf-8"), launcher.DEFAULT_SOURCE)
            self.assertIn("system DoorControl\n  entry control", launcher.DEFAULT_SOURCE)
            self.assertIn("in panel:PanelInput", launcher.DEFAULT_SOURCE)
            self.assertIn("out receipt:Receipt", launcher.DEFAULT_SOURCE)
            self.assertIn("!actuator(state:DoorState):Receipt", launcher.DEFAULT_SOURCE)

    def test_untouched_code_derived_default_is_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = launcher.default_input_path(root)
            path.parent.mkdir(parents=True)
            path.write_text(launcher.CODE_DERIVED_DEFAULT_SOURCE, encoding="utf-8")

            with patch.object(launcher.Path, "cwd", return_value=root):
                self.assertEqual(launcher.resolve_input(None), path)

            self.assertEqual(path.read_text(encoding="utf-8"), launcher.DEFAULT_SOURCE)

    def test_user_modified_legacy_workspace_is_not_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = launcher.default_input_path(root)
            path.parent.mkdir(parents=True)
            modified = launcher.LEGACY_DEFAULT_SOURCE + "# user note\n"
            path.write_text(modified, encoding="utf-8")

            with patch.object(launcher.Path, "cwd", return_value=root):
                launcher.resolve_input(None)

            self.assertEqual(path.read_text(encoding="utf-8"), modified)

    def test_explicit_input_is_preserved(self) -> None:
        explicit = Path("examples/state_diagrams/traffic_light.glyph")
        self.assertEqual(launcher.resolve_input(explicit), explicit)

    def test_main_starts_default_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(launcher.Path, "cwd", return_value=root),
                patch.object(launcher, "run_diagram_app", return_value=0) as run,
            ):
                self.assertEqual(launcher.main([]), 0)
                run.assert_called_once_with(root / ".glyph" / "workspace.glyph")


if __name__ == "__main__":
    unittest.main()

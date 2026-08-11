from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from glyph import (
    CompilationPipeline,
    GlyphStudio,
    IncrementalCompiler,
    compile_file,
    compile_source,
    parse_program,
)
from glyph.compiler import GlyphError


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "machine_assembly_immediate.glyph"


class MachineAssemblyEntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = EXAMPLE.read_text(encoding="utf-8")

    def test_public_parse_accepts_but_rust_compile_rejects_assembly(self) -> None:
        program = parse_program(self.source)
        self.assertTrue(program.declarations)

        with self.assertRaisesRegex(GlyphError, "Rust loweringは未実装"):
            compile_source(self.source)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generated.rs"
            with self.assertRaisesRegex(GlyphError, "Rust loweringは未実装"):
                compile_file(EXAMPLE, output)
            self.assertFalse(output.exists())

    def test_pipeline_and_incremental_paths_publish_analysis_artifacts(self) -> None:
        outputs = CompilationPipeline().compile_text(
            self.source,
            "machine_assembly_immediate.glyph",
        )
        self.assertEqual(outputs.model.assembly_ir[0].name, "DoorControl")
        self.assertIn("machine-assembly-ir.json", outputs.diagrams.files)
        self.assertIn("machine-assembly.mmd", outputs.diagrams.files)
        self.assertIn("Rust generation is blocked", outputs.artifacts.logic)
        self.assertNotIn("compile_error!", outputs.artifacts.logic)

        incremental = IncrementalCompiler().compile_text(
            self.source,
            "machine_assembly_immediate.glyph",
        )
        self.assertTrue(incremental.changed)
        self.assertEqual(incremental.snapshot.model.assembly_ir[0].name, "DoorControl")
        self.assertIn("machine-assembly-ir.json", incremental.snapshot.diagrams.files)

    def test_incremental_rust_write_rejects_without_touching_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generated.rs"
            compiler = IncrementalCompiler()
            with self.assertRaisesRegex(GlyphError, "Rust loweringは未実装"):
                compiler.compile_path(EXAMPLE, logic_output=output)
            self.assertFalse(output.exists())

    def test_studio_rebuild_accepts_assembly_and_writes_topology(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "assembly.glyph"
            source_path.write_text(self.source, encoding="utf-8")
            studio = GlyphStudio(source_path)
            snapshot = studio.rebuild()

            self.assertEqual(snapshot.status, "ready")
            self.assertIn("machine-assembly-ir.json", snapshot.artifacts)
            self.assertIn("machine-assembly.mmd", snapshot.artifacts)
            self.assertIn(
                "Rust generation is blocked",
                snapshot.artifacts["generated.rs"],
            )

    def test_glyphc_check_and_diagram_modes_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            diagrams = Path(directory) / "diagrams"
            check = subprocess.run(
                [sys.executable, str(ROOT / "glyphc.py"), str(EXAMPLE), "--check"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(check.returncode, 0, check.stderr)

            render = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "glyphc.py"),
                    str(EXAMPLE),
                    "--diagram-dir",
                    str(diagrams),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(render.returncode, 0, render.stderr)
            self.assertTrue((diagrams / "machine-assembly-ir.json").exists())
            self.assertTrue((diagrams / "machine-assembly.mmd").exists())

    def test_glyphc_rust_output_fails_nonzero_and_emits_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generated.rs"
            host_output = Path(directory) / "host.generated.rs"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "glyphc.py"),
                    str(EXAMPLE),
                    "-o",
                    str(output),
                    "--host-output",
                    str(host_output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Rust loweringは未実装", result.stderr)
            self.assertFalse(output.exists())
            self.assertFalse(host_output.exists())


if __name__ == "__main__":
    unittest.main()

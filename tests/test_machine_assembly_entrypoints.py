from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from glyph import CompilationPipeline, GlyphStudio, IncrementalCompiler, compile_file, compile_source, parse_program


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "machine_assembly_immediate.glyph"


class MachineAssemblyEntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = EXAMPLE.read_text(encoding="utf-8")

    def test_public_compile_and_parse_entrypoints_accept_assembly(self) -> None:
        program = parse_program(self.source)
        self.assertTrue(program.declarations)
        self.assertIn("compile_error!", compile_source(self.source))

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generated.rs"
            compile_file(EXAMPLE, output)
            self.assertIn("compile_error!", output.read_text(encoding="utf-8"))

    def test_pipeline_and_incremental_paths_publish_assembly_artifacts(self) -> None:
        outputs = CompilationPipeline().compile_text(
            self.source,
            "machine_assembly_immediate.glyph",
        )
        self.assertEqual(outputs.model.assembly_ir[0].name, "DoorControl")
        self.assertIn("machine-assembly-ir.json", outputs.diagrams.files)
        self.assertIn("machine-assembly.mmd", outputs.diagrams.files)
        self.assertIn("compile_error!", outputs.artifacts.logic)

        incremental = IncrementalCompiler().compile_text(
            self.source,
            "machine_assembly_immediate.glyph",
        )
        self.assertTrue(incremental.changed)
        self.assertEqual(incremental.snapshot.model.assembly_ir[0].name, "DoorControl")
        self.assertIn("machine-assembly-ir.json", incremental.snapshot.diagrams.files)

    def test_studio_rebuild_accepts_assembly_and_writes_topology(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "assembly.glyph"
            source_path.write_text(self.source, encoding="utf-8")
            studio = GlyphStudio(source_path)
            snapshot = studio.rebuild()

            self.assertEqual(snapshot.status, "ready")
            self.assertIn("machine-assembly-ir.json", snapshot.artifacts)
            self.assertIn("machine-assembly.mmd", snapshot.artifacts)
            self.assertIn("compile_error!", snapshot.artifacts["generated.rs"])

    def test_glyphc_cli_accepts_assembly_through_canonical_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generated.rs"
            host_output = Path(directory) / "host.generated.rs"
            diagrams = Path(directory) / "diagrams"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "glyphc.py"),
                    str(EXAMPLE),
                    "-o",
                    str(output),
                    "--host-output",
                    str(host_output),
                    "--diagram-dir",
                    str(diagrams),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("compile_error!", output.read_text(encoding="utf-8"))
            self.assertTrue(host_output.exists())
            self.assertTrue((diagrams / "machine-assembly-ir.json").exists())
            self.assertTrue((diagrams / "machine-assembly.mmd").exists())


if __name__ == "__main__":
    unittest.main()

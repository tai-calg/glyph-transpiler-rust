from __future__ import annotations

import unittest

import glyph


_STABLE_PUBLIC_API = {
    "CompilationModel",
    "CompilationOutputs",
    "CompilationPipeline",
    "CompilationSnapshot",
    "DiagramBundle",
    "GlyphError",
    "GlyphStudio",
    "IncrementalCompiler",
    "IncrementalResult",
    "PreprocessResult",
    "RawMacroDef",
    "RustArtifacts",
    "SemanticModel",
    "StudioSnapshot",
    "SymbolId",
    "SymbolRecord",
    "compile_artifact_files",
    "compile_artifacts",
    "compile_diagram_bundle",
    "compile_file",
    "compile_outputs",
    "compile_source",
    "parse_artifact_model",
    "parse_compilation_model",
    "parse_program",
    "preprocess_source",
    "run_studio",
    "write_diagram_bundle",
}


class PublicApiTests(unittest.TestCase):
    def test_package_root_preserves_the_pre_glyph04_api(self) -> None:
        self.assertEqual(set(glyph.__all__), _STABLE_PUBLIC_API)
        for name in _STABLE_PUBLIC_API:
            self.assertTrue(hasattr(glyph, name), name)

    def test_internal_ir_and_builder_types_are_not_reexported(self) -> None:
        internal_names = {
            "CapabilityModel",
            "ContractModel",
            "ContractSemanticModel",
            "HostRequirementModel",
            "build_host_requirements",
            "render_host_binding_trait",
        }

        self.assertTrue(internal_names.isdisjoint(glyph.__all__))


if __name__ == "__main__":
    unittest.main()

from .artifacts import (
    CompilationModel,
    RustArtifacts,
    compile_artifact_files,
    compile_artifacts,
    parse_artifact_model,
    parse_compilation_model,
)
from .compilation import (
    CompilationOutputs,
    CompilationPipeline,
    compile_diagram_bundle,
    compile_outputs,
    write_diagram_bundle,
)
from .compiler import GlyphError
from .frontend import compile_file, compile_source, parse_program
from .incremental import CompilationSnapshot, IncrementalCompiler, IncrementalResult
from .mermaid import DiagramBundle
from .preprocessor import (
    PreprocessResult,
    RawMacroDef,
    preprocess_source as _preprocess_source,
)
from .semantic import SemanticModel
from .studio import GlyphStudio, StudioSnapshot, run_studio
from .symbols import SymbolId, SymbolRecord
from .temporal_sigils import reject_reserved_temporal_macro_names


def preprocess_source(source: str) -> PreprocessResult:
    """Run the public raw preprocessor with language-level name reservations."""

    reject_reserved_temporal_macro_names(source)
    return _preprocess_source(source)


# Keep the package root as the stable user-facing facade. Glyph 0.4 IR models,
# semantic builders, validators, and code generators remain available from
# their responsibility-specific modules but are deliberately not re-exported.
__all__ = [
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
]

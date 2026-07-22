from .artifacts import (
    CompilationModel,
    RustArtifacts,
    compile_artifact_files,
    compile_artifacts,
    parse_artifact_model,
    parse_compilation_model,
)
from .capabilities import (
    AggregateType,
    CapabilityExtraction,
    CapabilityFunction,
    CapabilityKind,
    CapabilityModel,
    CapabilityOperation,
    CapabilityParam,
    CapabilityType,
    ResourceDecl,
    extract_capabilities,
    parse_capability_type,
)
from .compilation import (
    CompilationOutputs,
    CompilationPipeline,
    compile_diagram_bundle,
    compile_outputs,
    write_diagram_bundle,
)
from .compiler import GlyphError
from .contracts import (
    ContractApplication,
    ContractDecl,
    ContractExtraction,
    ContractKind,
    ContractModel,
    ContractRef,
    extract_contracts,
)
from .contract_semantics import (
    AppliedContract,
    ContractRow,
    ContractSemanticModel,
    HandlerContract,
    HandlerStep,
    LawContract,
    ProtocolContract,
    ProtocolNode,
    WorldContract,
    build_contract_semantics,
    parse_protocol,
)
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


__all__ = [
    "AggregateType",
    "AppliedContract",
    "CapabilityExtraction",
    "CapabilityFunction",
    "CapabilityKind",
    "CapabilityModel",
    "CapabilityOperation",
    "CapabilityParam",
    "CapabilityType",
    "CompilationModel",
    "CompilationOutputs",
    "CompilationPipeline",
    "CompilationSnapshot",
    "ContractApplication",
    "ContractDecl",
    "ContractExtraction",
    "ContractKind",
    "ContractModel",
    "ContractRef",
    "ContractRow",
    "ContractSemanticModel",
    "DiagramBundle",
    "GlyphError",
    "GlyphStudio",
    "HandlerContract",
    "HandlerStep",
    "IncrementalCompiler",
    "IncrementalResult",
    "LawContract",
    "PreprocessResult",
    "ProtocolContract",
    "ProtocolNode",
    "RawMacroDef",
    "ResourceDecl",
    "RustArtifacts",
    "SemanticModel",
    "StudioSnapshot",
    "SymbolId",
    "SymbolRecord",
    "WorldContract",
    "build_contract_semantics",
    "compile_artifact_files",
    "compile_artifacts",
    "compile_diagram_bundle",
    "compile_file",
    "compile_outputs",
    "compile_source",
    "extract_capabilities",
    "extract_contracts",
    "parse_artifact_model",
    "parse_capability_type",
    "parse_compilation_model",
    "parse_program",
    "parse_protocol",
    "preprocess_source",
    "run_studio",
    "write_diagram_bundle",
]

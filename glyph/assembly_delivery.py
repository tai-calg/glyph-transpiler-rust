from __future__ import annotations


def install_machine_assembly_delivery() -> None:
    """Install Assembly-aware entrypoints without scanning or mutating models.

    The legacy parser/code generator remain captured privately by
    `assembly_frontend`. Public entrypoints are rebound once to the immutable
    Assembly model and to the analysis-safe Rust artifact path used by Studio.
    """

    from . import artifacts as artifacts_module
    from . import compilation as compilation_module
    from . import mermaid as mermaid_module
    from .assembly_frontend import (
        build_analysis_rust_artifacts,
        compile_artifact_files,
        compile_artifacts,
        parse_artifact_model,
        parse_compilation_model,
    )

    artifacts_module.parse_compilation_model = parse_compilation_model
    artifacts_module.parse_artifact_model = parse_artifact_model
    artifacts_module.compile_artifacts = compile_artifacts
    artifacts_module.compile_artifact_files = compile_artifact_files

    # CompilationPipeline must remain usable for checking, Studio and diagrams
    # while Rust generation is explicitly reported as blocked.
    compilation_module.parse_compilation_model = parse_compilation_model
    compilation_module.build_rust_artifacts = build_analysis_rust_artifacts
    mermaid_module.parse_compilation_model = parse_compilation_model

from .artifacts import CompilationModel, RustArtifacts
from .compilation import (
    CompilationOutputs,
    CompilationPipeline,
    compile_diagram_bundle,
    compile_outputs,
    write_diagram_bundle,
)
from .tooling_delivery_v2 import install_tooling_delivery_v2 as _install_tooling_delivery_v2

_install_tooling_delivery_v2()
del _install_tooling_delivery_v2

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

# Studio diagnostics retain their canonical message while exposing Japanese and
# English variants to the browser. The HTML enhancer is applied here so every
# import path, including the desktop server, receives the same default-Japanese
# selector without duplicating the Studio document.
from . import studio as _studio_module
from .diagnostic_i18n import localize_message_payload as _localize_message_payload
from .studio_locale import enhance_studio_locale_html as _enhance_studio_locale_html

_original_studio_snapshot_to_dict = StudioSnapshot.to_dict


def _localized_studio_snapshot_to_dict(
    self: StudioSnapshot,
    source_path,
    output_dir,
    _original=_original_studio_snapshot_to_dict,
    _localize=_localize_message_payload,
):
    return _localize(_original(self, source_path, output_dir))


_localized_studio_snapshot_to_dict.__glyph_localized__ = True
if not getattr(StudioSnapshot.to_dict, "__glyph_localized__", False):
    StudioSnapshot.to_dict = _localized_studio_snapshot_to_dict

_studio_module.STUDIO_HTML = _enhance_studio_locale_html(_studio_module.STUDIO_HTML)
_studio_module._studio_ui.STUDIO_HTML = _studio_module.STUDIO_HTML


def preprocess_source(source: str) -> PreprocessResult:
    """Run the public raw preprocessor with language-level name reservations."""

    reject_reserved_temporal_macro_names(source)
    return _preprocess_source(source)


# Install Assembly-aware canonical entrypoints after the public modules have
# loaded. Unlike the initial prototype, this does not scan sys.modules and does
# not mutate frozen CompilationModel instances.
from .assembly_delivery import (
    install_machine_assembly_delivery as _install_machine_assembly_delivery,
)

_install_machine_assembly_delivery()
del _install_machine_assembly_delivery

from .assembly_tooling_delivery import (
    install_machine_assembly_tooling_delivery as _install_machine_assembly_tooling_delivery,
)

_install_machine_assembly_tooling_delivery()
del _install_machine_assembly_tooling_delivery

from .assembly_frontend import (
    compile_artifact_files,
    compile_artifacts,
    parse_artifact_model,
    parse_compilation_model,
)


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

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from .architecture import (
    ArchitectureIR,
    SystemDecl,
    build_architecture_ir,
    extract_systems,
)
from .ast_macros import (
    AstMacroDef,
    expand_function_macros,
    expand_machine_macros,
    expand_program_macros,
    extract_ast_macros,
)
from .capabilities import CapabilityModel
from .capability_codegen import lower_capability_codegen
from .capability_model_validate import validate_capability_model
from .capability_places import extract_capabilities_with_places
from .capability_surface_validate import validate_capability_surface
from .capability_type_normalize import normalize_capability_types
from .compiler import ExternDecl, FunctionDecl, GlyphError, Program, parse_program
from .contract_application_binding import bind_field_applications_for_semantics
from .contract_law_bridge import build_contract_law_specs
from .contract_semantics import ContractSemanticModel, build_contract_semantics
from .contract_type_normalize import normalize_contract_types
from .contracts import ContractModel, extract_contracts, remap_contract_lines
from .function_blocks import (
    FunctionBlockLowering,
    lower_function_blocks,
    restore_block_source_lines,
)
from .functional import FunctionalPatternRustGenerator, validate_function_values
from .layout import normalize_multiline_declarations
from .machine import MachineDecl, extract_machines, validate_machines
from .opaque import (
    OpaqueAwareRustGenerator,
    OpaqueDecl,
    expose_opaque_as_pure,
    generate_manual_scaffold,
    lower_opaque_to_extern,
    mask_opaque_as_effect,
    relabel_architecture,
    relabel_semantic_model,
    without_opaque_externs,
)
from .pipeline import (
    LambdaLowering,
    join_pipeline_continuations,
    lower_lambda_pipelines,
    restore_lambda_source_lines,
)
from .preprocessor import PreprocessResult, preprocess_source, remap_source_lines
from .runtime_contract_validate import validate_and_refine_runtime_contracts
from .semantic import SemanticModel, build_semantic_model
from .syntax import expand_compact_syntax
from .temporal import SpecDecl, extract_specs
from .temporal_codegen import append_temporal_rust
from .temporal_sigils import (
    normalize_temporal_sigils,
    reject_reserved_temporal_macro_names,
)
from .temporal_stream_codegen import append_streaming_temporal_rust
from .temporal_stream_safety_codegen import append_safety_streaming_temporal_rust
from .temporal_validate import validate_temporal_specs


_CAPABILITY_TYPE_USE = re.compile(
    r"(?:^|[(:,|])\s*(?:own|share|link)\s+[A-Za-z_&]"
)


@dataclass(frozen=True)
class RustArtifacts:
    logic: str
    host: str
    manual_scaffold: str = ""


@dataclass(frozen=True)
class ExpandedCompilation:
    """Compiler-internal model whose source lines refer to preprocessed input."""

    program: Program
    inline_effects: tuple[FunctionDecl, ...]
    specs: tuple[SpecDecl, ...]
    machines: tuple[MachineDecl, ...]
    systems: tuple[SystemDecl, ...]
    ast_macros: tuple[AstMacroDef, ...]
    blocks: tuple[FunctionBlockLowering, ...]
    lambdas: tuple[LambdaLowering, ...]
    opaques: tuple[OpaqueDecl, ...]
    capabilities: CapabilityModel = field(default_factory=CapabilityModel.empty)
    contracts: ContractModel = field(default_factory=ContractModel.empty)
    runtime_contracts: ContractSemanticModel = field(
        default_factory=ContractSemanticModel.empty
    )


@dataclass(frozen=True)
class CompilationModel:
    program: Program
    inline_effects: tuple[FunctionDecl, ...]
    specs: tuple[SpecDecl, ...]
    machines: tuple[MachineDecl, ...]
    systems: tuple[SystemDecl, ...]
    architecture: ArchitectureIR
    ast_macros: tuple[AstMacroDef, ...]
    blocks: tuple[FunctionBlockLowering, ...]
    lambdas: tuple[LambdaLowering, ...]
    opaques: tuple[OpaqueDecl, ...]
    semantic: SemanticModel
    preprocess: PreprocessResult
    expanded: ExpandedCompilation
    capabilities: CapabilityModel = field(default_factory=CapabilityModel.empty)
    contracts: ContractModel = field(default_factory=ContractModel.empty)
    runtime_contracts: ContractSemanticModel = field(
        default_factory=ContractSemanticModel.empty
    )


@dataclass(frozen=True)
class _ParsedCore:
    program: Program
    inline_effects: tuple[FunctionDecl, ...]
    specs: tuple[SpecDecl, ...]
    machines: tuple[MachineDecl, ...]
    systems: tuple[SystemDecl, ...]
    ast_macros: tuple[AstMacroDef, ...]
    blocks: tuple[FunctionBlockLowering, ...]
    lambdas: tuple[LambdaLowering, ...]
    opaques: tuple[OpaqueDecl, ...]

    def with_specs(self, specs: tuple[SpecDecl, ...]) -> "_ParsedCore":
        return _ParsedCore(
            self.program,
            self.inline_effects,
            specs,
            self.machines,
            self.systems,
            self.ast_macros,
            self.blocks,
            self.lambdas,
            self.opaques,
        )


def _inline_effect_lines(source: str) -> set[int]:
    lines: set[int] = set()
    for line_no, original in enumerate(source.splitlines(), start=1):
        clean = original.split("#", 1)[0].rstrip()
        if (
            clean
            and not clean[0].isspace()
            and clean.startswith("!")
            and "=" in clean
        ):
            lines.add(line_no)
    return lines


def _parse_effect_program(
    source: str,
) -> tuple[Program, tuple[FunctionDecl, ...]]:
    inline_lines = _inline_effect_lines(source)
    transformed: list[str] = []
    for line_no, original in enumerate(source.splitlines(), start=1):
        if line_no in inline_lines:
            bang = original.index("!")
            original = original[:bang] + ">" + original[bang + 1 :]
        transformed.append(original)

    parsed = parse_program("\n".join(transformed))
    effects: list[FunctionDecl] = []
    logic = []
    for declaration in parsed.declarations:
        if isinstance(declaration, FunctionDecl) and declaration.line in inline_lines:
            effects.append(declaration)
            logic.append(
                ExternDecl(
                    declaration.name,
                    declaration.params,
                    declaration.return_type,
                    declaration.line,
                )
            )
        else:
            logic.append(declaration)
    return Program(tuple(logic)), tuple(effects)


def generate_host_rust(
    program: Program,
    inline_effects: tuple[FunctionDecl, ...],
    opaques: tuple[OpaqueDecl, ...],
) -> str:
    """Generate the ordinary `!` boundary scaffold for one parsed program."""

    generator = FunctionalPatternRustGenerator(program)
    inline_by_name = {declaration.name: declaration for declaration in inline_effects}
    opaque_names = {declaration.name for declaration in opaques}
    output = [
        "// @generated by glyphc. Do not edit by hand.",
        "use crate::generated::*;",
        "",
    ]
    for declaration in program.declarations:
        if not isinstance(declaration, ExternDecl) or declaration.name in opaque_names:
            continue
        signature = generator._signature_tail(
            declaration.params,
            declaration.return_type,
        )
        output.append("#[allow(unused_variables)]")
        output.append(f"pub fn {declaration.name}{signature} {{")
        implementation = inline_by_name.get(declaration.name)
        if implementation is None:
            output.append(
                f'    panic!("Glyph effect boundary `{declaration.name}` is not connected")'
            )
        elif implementation.expression is not None:
            output.append(f"    {generator._expr(implementation.expression)}")
        else:
            raise GlyphError(
                f"{implementation.line}行目: !境界の試作実装は単一式で記述する"
            )
        output.extend(["}", ""])
    return "\n".join(output).rstrip() + "\n"


def _uses_glyph04_syntax(source: str) -> bool:
    """Detect only opt-in syntax introduced by Glyph 0.4.

    Legacy boolean `&`, ordinary identifiers named `own`, and comments do not
    activate the new pipeline. Malformed legacy input therefore reaches the
    original parser and preserves its diagnostics.
    """

    for original in source.splitlines():
        code = original.split("#", 1)[0]
        stripped = code.strip()
        if not stripped:
            continue
        if stripped.startswith("'") or stripped.startswith("resource "):
            return True
        if "@{" in code or "&mut " in code:
            return True
        if " as share" in code or " as link" in code:
            return True
        if _CAPABILITY_TYPE_USE.search(code):
            return True
    return False


def _parse_core(source: str) -> _ParsedCore:
    masked, opaque_seeds = mask_opaque_as_effect(source)
    without_systems, systems = extract_systems(masked)
    joined = join_pipeline_continuations(without_systems)
    compact = expand_compact_syntax(joined)
    without_ast_macros, ast_macros = extract_ast_macros(compact)
    pure_source, opaques = expose_opaque_as_pure(
        without_ast_macros,
        opaque_seeds,
    )
    block_result = lower_function_blocks(pure_source, ast_macros)
    pipeline_result = lower_lambda_pipelines(block_result.source)
    parser_source = lower_opaque_to_extern(
        pipeline_result.source,
        opaque_seeds,
    )
    without_specs, specs = extract_specs(parser_source)
    core, machines = extract_machines(without_specs)
    program, inline_effects = _parse_effect_program(core)

    program = expand_program_macros(program, ast_macros)
    program = restore_block_source_lines(program, block_result.blocks)
    lambdas = (*block_result.lambdas, *pipeline_result.lambdas)
    program = restore_lambda_source_lines(program, lambdas)
    inline_effects = expand_function_macros(inline_effects, ast_macros)
    machines = expand_machine_macros(machines, ast_macros)

    return _ParsedCore(
        program,
        inline_effects,
        specs,
        machines,
        systems,
        ast_macros,
        block_result.blocks,
        tuple(lambdas),
        opaques,
    )


def _validate_core(core: _ParsedCore, *, temporal: bool) -> None:
    validate_function_values(without_opaque_externs(core.program, core.opaques))
    if temporal:
        validate_temporal_specs(core.program, core.specs)
    validate_machines(core.program, core.machines)


def _finalize_model(
    source_name: str,
    preprocess: PreprocessResult,
    core: _ParsedCore,
    capabilities: CapabilityModel = CapabilityModel(),
    contracts: ContractModel = ContractModel(),
    runtime_contracts: ContractSemanticModel = ContractSemanticModel(),
) -> CompilationModel:
    expanded = ExpandedCompilation(
        core.program,
        core.inline_effects,
        core.specs,
        core.machines,
        core.systems,
        core.ast_macros,
        core.blocks,
        core.lambdas,
        core.opaques,
        capabilities,
        contracts,
        runtime_contracts,
    )

    program = remap_source_lines(core.program, preprocess)
    inline_effects = remap_source_lines(core.inline_effects, preprocess)
    specs = remap_source_lines(core.specs, preprocess)
    machines = remap_source_lines(core.machines, preprocess)
    systems = remap_source_lines(core.systems, preprocess)
    ast_macros = remap_source_lines(core.ast_macros, preprocess)
    blocks = remap_source_lines(core.blocks, preprocess)
    lambdas = remap_source_lines(core.lambdas, preprocess)
    opaques = remap_source_lines(core.opaques, preprocess)
    public_contracts = remap_contract_lines(contracts, preprocess.source_line)

    semantic = relabel_semantic_model(
        build_semantic_model(program, machines, ast_macros, specs),
        opaques,
    )
    architecture = relabel_architecture(
        build_architecture_ir(source_name, program, systems),
        opaques,
    )
    return CompilationModel(
        program,
        inline_effects,
        specs,
        machines,
        systems,
        architecture,
        ast_macros,
        blocks,
        lambdas,
        opaques,
        semantic,
        preprocess,
        expanded,
        capabilities,
        public_contracts,
        runtime_contracts,
    )


def _parse_legacy_compilation_model(
    source_name: str,
    preprocess: PreprocessResult,
) -> CompilationModel:
    """Run the exact pre-0.4 path for sources that do not opt in."""

    try:
        core = _parse_core(normalize_temporal_sigils(preprocess.source))
        _validate_core(core, temporal=True)
    except GlyphError as exc:
        raise preprocess.remap_error(exc) from exc
    return _finalize_model(source_name, preprocess, core)


def _parse_glyph04_compilation_model(
    source_name: str,
    preprocess: PreprocessResult,
) -> CompilationModel:
    try:
        expanded_source = normalize_temporal_sigils(preprocess.source)
        contract_result = extract_contracts(expanded_source)
        canonical_contracts = normalize_contract_types(contract_result.model)

        layout = normalize_multiline_declarations(contract_result.source)
        validate_capability_surface(layout.source)
        capability_result = extract_capabilities_with_places(layout.source)
        canonical_capabilities = normalize_capability_types(capability_result.model)
        validate_capability_model(canonical_capabilities)

        codegen_source = lower_capability_codegen(
            layout.source,
            capability_result.source,
        )
        core = _parse_core(codegen_source)
        _validate_core(core, temporal=False)

        semantic_source = bind_field_applications_for_semantics(expanded_source)
        runtime_contracts = build_contract_semantics(
            semantic_source,
            canonical_contracts,
            canonical_capabilities,
            core.program,
        )
        runtime_contracts = validate_and_refine_runtime_contracts(
            expanded_source,
            runtime_contracts,
            canonical_contracts,
            canonical_capabilities,
            core.program,
        )
        contract_specs = build_contract_law_specs(
            contract_result.model,
            runtime_contracts,
            core.program,
        )
        core = core.with_specs((*core.specs, *contract_specs))
        validate_temporal_specs(core.program, core.specs)
    except GlyphError as exc:
        raise preprocess.remap_error(exc) from exc

    return _finalize_model(
        source_name,
        preprocess,
        core,
        capability_result.model,
        contract_result.model,
        runtime_contracts,
    )


def parse_compilation_model(
    source: str,
    source_name: str = "input.glyph",
) -> CompilationModel:
    """Preprocess, parse, validate, and assemble one shared design model."""

    reject_reserved_temporal_macro_names(source)
    preprocess = preprocess_source(source)
    if _uses_glyph04_syntax(preprocess.source):
        return _parse_glyph04_compilation_model(source_name, preprocess)
    return _parse_legacy_compilation_model(source_name, preprocess)


def parse_artifact_model(
    source: str,
) -> tuple[
    Program,
    tuple[FunctionDecl, ...],
    tuple[SpecDecl, ...],
    tuple[MachineDecl, ...],
]:
    model = parse_compilation_model(source)
    return model.program, model.inline_effects, model.specs, model.machines


def build_rust_artifacts(model: CompilationModel) -> RustArtifacts:
    logic = OpaqueAwareRustGenerator(
        model.program,
        model.opaques,
        model.blocks,
    ).generate()
    logic = append_temporal_rust(logic, model.program, model.specs)
    logic = append_streaming_temporal_rust(logic, model.program, model.specs)
    logic = append_safety_streaming_temporal_rust(
        logic,
        model.program,
        model.specs,
    )
    return RustArtifacts(
        logic,
        generate_host_rust(model.program, model.inline_effects, model.opaques),
        generate_manual_scaffold(model.program, model.opaques),
    )


def compile_artifacts(source: str) -> RustArtifacts:
    return build_rust_artifacts(parse_compilation_model(source))


def compile_artifact_files(
    input_path: str | Path,
    logic_output_path: str | Path,
    host_output_path: str | Path,
) -> None:
    artifacts = compile_artifacts(Path(input_path).read_text(encoding="utf-8"))

    logic_output = Path(logic_output_path)
    logic_output.parent.mkdir(parents=True, exist_ok=True)
    logic_output.write_text(artifacts.logic, encoding="utf-8")

    host_output = Path(host_output_path)
    host_output.parent.mkdir(parents=True, exist_ok=True)
    host_output.write_text(artifacts.host, encoding="utf-8")

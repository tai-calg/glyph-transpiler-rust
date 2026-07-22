from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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
from .capabilities import CapabilityModel, extract_capabilities
from .capability_surface_validate import validate_capability_surface
from .compiler import ExternDecl, FunctionDecl, GlyphError, Program, parse_program
from .contracts import ContractModel, extract_contracts, remap_contract_lines
from .contract_semantics import ContractSemanticModel, build_contract_semantics
from .function_blocks import (
    FunctionBlockLowering,
    lower_function_blocks,
    restore_block_source_lines,
)
from .functional import FunctionalPatternRustGenerator, validate_function_values
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


@dataclass(frozen=True)
class RustArtifacts:
    logic: str
    host: str
    manual_scaffold: str = ""


@dataclass(frozen=True)
class ExpandedCompilation:
    """Compiler-internal model whose lines refer to `preprocess.source`."""

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


def _inline_effect_lines(source: str) -> set[int]:
    lines: set[int] = set()
    for line_no, original in enumerate(source.splitlines(), start=1):
        clean = original.split("#", 1)[0].rstrip()
        if not clean or clean[0].isspace() or not clean.startswith("!"):
            continue
        if "=" in clean:
            lines.add(line_no)
    return lines


def _parse_effect_program(source: str) -> tuple[Program, tuple[FunctionDecl, ...]]:
    inline_lines = _inline_effect_lines(source)
    transformed: list[str] = []
    for line_no, original in enumerate(source.splitlines(), start=1):
        if line_no in inline_lines:
            bang = original.index("!")
            original = original[:bang] + ">" + original[bang + 1 :]
        transformed.append(original)

    parsed = parse_program("\n".join(transformed))
    effects: list[FunctionDecl] = []
    logic_declarations = []
    for decl in parsed.declarations:
        if isinstance(decl, FunctionDecl) and decl.line in inline_lines:
            effects.append(decl)
            logic_declarations.append(
                ExternDecl(decl.name, decl.params, decl.return_type, decl.line)
            )
        else:
            logic_declarations.append(decl)
    return Program(tuple(logic_declarations)), tuple(effects)


def _generate_host(
    program: Program,
    inline_effects: tuple[FunctionDecl, ...],
    opaques: tuple[OpaqueDecl, ...],
) -> str:
    generator = FunctionalPatternRustGenerator(program)
    inline_by_name = {decl.name: decl for decl in inline_effects}
    opaque_names = {decl.name for decl in opaques}
    externs = [
        decl
        for decl in program.declarations
        if isinstance(decl, ExternDecl) and decl.name not in opaque_names
    ]

    out = [
        "// @generated by glyphc. Do not edit by hand.",
        "use crate::generated::*;",
        "",
    ]
    for decl in externs:
        signature = generator._signature_tail(decl.params, decl.return_type)
        out.append("#[allow(unused_variables)]")
        out.append(f"pub fn {decl.name}{signature} {{")
        implementation = inline_by_name.get(decl.name)
        if implementation is None:
            out.append(
                f'    panic!("Glyph effect boundary `{decl.name}` is not connected")'
            )
        elif implementation.expression is not None:
            out.append(f"    {generator._expr(implementation.expression)}")
        else:
            raise GlyphError(
                f"{implementation.line}行目: !境界の試作実装は単一式で記述する"
            )
        out.extend(["}", ""])
    return "\n".join(out).rstrip() + "\n"


def parse_compilation_model(
    source: str,
    source_name: str = "input.glyph",
) -> CompilationModel:
    """Preprocess, parse, lower, validate, and build one shared design model."""

    reject_reserved_temporal_macro_names(source)
    preprocess = preprocess_source(source)

    try:
        expanded_source = normalize_temporal_sigils(preprocess.source)
        contract_result = extract_contracts(expanded_source)
        validate_capability_surface(contract_result.source)
        capability_result = extract_capabilities(contract_result.source)
        masked, opaque_seeds = mask_opaque_as_effect(capability_result.source)
        without_systems, systems = extract_systems(masked)
        joined = join_pipeline_continuations(without_systems)
        compact = expand_compact_syntax(joined)
        without_ast_macros, ast_macros = extract_ast_macros(compact)
        pure_source, opaques = expose_opaque_as_pure(
            without_ast_macros, opaque_seeds
        )
        block_result = lower_function_blocks(pure_source, ast_macros)
        pipeline_result = lower_lambda_pipelines(block_result.source)
        parser_source = lower_opaque_to_extern(
            pipeline_result.source, opaque_seeds
        )
        without_specs, specs = extract_specs(parser_source)
        core, machines = extract_machines(without_specs)
        program, inline_effects = _parse_effect_program(core)

        program = expand_program_macros(program, ast_macros)
        program = restore_block_source_lines(program, block_result.blocks)
        combined_lambdas = (*block_result.lambdas, *pipeline_result.lambdas)
        program = restore_lambda_source_lines(program, combined_lambdas)
        inline_effects = expand_function_macros(inline_effects, ast_macros)
        machines = expand_machine_macros(machines, ast_macros)

        validate_function_values(without_opaque_externs(program, opaques))
        validate_temporal_specs(program, specs)
        validate_machines(program, machines)
        runtime_contracts = build_contract_semantics(
            expanded_source,
            contract_result.model,
            capability_result.model,
            program,
        )
    except GlyphError as exc:
        raise preprocess.remap_error(exc) from exc

    expanded = ExpandedCompilation(
        program,
        inline_effects,
        specs,
        machines,
        systems,
        ast_macros,
        block_result.blocks,
        tuple(combined_lambdas),
        opaques,
        capability_result.model,
        contract_result.model,
        runtime_contracts,
    )

    program = remap_source_lines(program, preprocess)
    inline_effects = remap_source_lines(inline_effects, preprocess)
    specs = remap_source_lines(specs, preprocess)
    machines = remap_source_lines(machines, preprocess)
    systems = remap_source_lines(systems, preprocess)
    ast_macros = remap_source_lines(ast_macros, preprocess)
    blocks = remap_source_lines(block_result.blocks, preprocess)
    combined_lambdas = remap_source_lines(tuple(combined_lambdas), preprocess)
    opaques = remap_source_lines(opaques, preprocess)
    contracts = remap_contract_lines(contract_result.model, preprocess.source_line)
    capabilities = capability_result.model

    semantic = relabel_semantic_model(
        build_semantic_model(program, machines, ast_macros, specs), opaques
    )
    architecture = relabel_architecture(
        build_architecture_ir(source_name, program, systems), opaques
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
        tuple(combined_lambdas),
        opaques,
        semantic,
        preprocess,
        expanded,
        capabilities,
        contracts,
        runtime_contracts,
    )


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


def compile_artifacts(source: str) -> RustArtifacts:
    model = parse_compilation_model(source)
    logic = append_temporal_rust(
        OpaqueAwareRustGenerator(
            model.program, model.opaques, model.blocks
        ).generate(),
        model.program,
        model.specs,
    )
    logic = append_streaming_temporal_rust(logic, model.program, model.specs)
    logic = append_safety_streaming_temporal_rust(
        logic, model.program, model.specs
    )
    host = _generate_host(model.program, model.inline_effects, model.opaques)
    manual_scaffold = generate_manual_scaffold(model.program, model.opaques)
    return RustArtifacts(
        logic=logic,
        host=host,
        manual_scaffold=manual_scaffold,
    )


def compile_artifact_files(
    input_path: str | Path,
    logic_output_path: str | Path,
    host_output_path: str | Path,
) -> None:
    source = Path(input_path).read_text(encoding="utf-8")
    artifacts = compile_artifacts(source)

    logic_output = Path(logic_output_path)
    logic_output.parent.mkdir(parents=True, exist_ok=True)
    logic_output.write_text(artifacts.logic, encoding="utf-8")

    host_output = Path(host_output_path)
    host_output.parent.mkdir(parents=True, exist_ok=True)
    host_output.write_text(artifacts.host, encoding="utf-8")

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

from .assembly import (
    AssemblyDecl,
    MachineAssemblyIR,
    _reachable_effects,
    extract_assemblies,
    has_top_level_assembly,
    validate_assemblies,
)
from .artifacts import (
    CompilationModel,
    ExpandedCompilation,
    RustArtifacts,
    build_rust_artifacts as _build_legacy_rust_artifacts,
    parse_compilation_model as _parse_legacy_compilation_model,
)
from .compiler import ExternDecl, FunctionDecl, GlyphError, Program
from .machine import MachineDecl
from .temporal import SpecDecl


_RUST_CODEGEN_ERROR = (
    "Machine Assemblyのinstance-aware Rust loweringは未実装。"
    "--check、図、設計JSONは生成できるがRust出力は生成できない"
)
_BLOCKED_LOGIC = (
    "// Machine Assembly Rust generation is blocked.\n"
    "// Use --check, typed design JSON, and machine-assembly-ir.json.\n"
)
_BLOCKED_HOST = (
    "// Machine Assembly Host generation is blocked until instance-aware lowering exists.\n"
)


@dataclass(frozen=True)
class AssemblyExpandedCompilation(ExpandedCompilation):
    assemblies: tuple[AssemblyDecl, ...] = ()
    assembly_ir: tuple[MachineAssemblyIR, ...] = ()


@dataclass(frozen=True)
class AssemblyCompilationModel(CompilationModel):
    assemblies: tuple[AssemblyDecl, ...] = ()
    assembly_ir: tuple[MachineAssemblyIR, ...] = ()
    assembly_source: str = ""


def _field_values(value: object, model_type: type) -> dict[str, object]:
    return {field.name: getattr(value, field.name) for field in fields(model_type)}


def _validate_route_sources_are_actions(
    base: CompilationModel,
    assemblies: tuple[AssemblyDecl, ...],
) -> None:
    """Report guard-only/non-action routes before payload signature diagnostics."""

    machines = {machine.name: machine for machine in base.machines}
    functions = {
        item.name: item
        for item in base.program.declarations
        if isinstance(item, FunctionDecl)
    }
    effects = {
        item.name: item
        for item in base.program.declarations
        if isinstance(item, ExternDecl)
    }
    inline_effects = {item.name: item for item in base.inline_effects}

    for assembly in assemblies:
        instance_machines = {
            instance.name: machines.get(instance.machine)
            for instance in assembly.instances
        }
        reachable_cache: dict[str, set[str]] = {}
        for route in assembly.routes:
            machine = instance_machines.get(route.source_instance)
            if machine is None or route.effect not in effects:
                continue
            reachable = reachable_cache.get(route.source_instance)
            if reachable is None:
                reachable = _reachable_effects(
                    machine,
                    functions,
                    effects,
                    inline_effects,
                )
                reachable_cache[route.source_instance] = reachable
            if route.effect not in reachable:
                raise GlyphError(
                    f"{route.line}行目: effect '{route.effect}' はMachine "
                    f"'{machine.name}' の遷移Actionから到達できない"
                )


def parse_compilation_model(
    source: str,
    source_name: str = "input.glyph",
) -> CompilationModel:
    if not has_top_level_assembly(source):
        return _parse_legacy_compilation_model(source, source_name)

    parser_source, assemblies = extract_assemblies(source)
    base = _parse_legacy_compilation_model(parser_source, source_name)
    _validate_route_sources_are_actions(base, assemblies)
    assembly_ir = validate_assemblies(
        base.program,
        base.machines,
        assemblies,
        base.inline_effects,
    )

    expanded_values = _field_values(base.expanded, ExpandedCompilation)
    expanded = AssemblyExpandedCompilation(
        **expanded_values,
        assemblies=assemblies,
        assembly_ir=assembly_ir,
    )
    model_values = _field_values(base, CompilationModel)
    model_values["expanded"] = expanded
    return AssemblyCompilationModel(
        **model_values,
        assemblies=assemblies,
        assembly_ir=assembly_ir,
        assembly_source=source,
    )


def has_assemblies(model: object) -> bool:
    return bool(getattr(model, "assembly_ir", ()))


def rust_codegen_error(model: object) -> str | None:
    return _RUST_CODEGEN_ERROR if has_assemblies(model) else None


def require_rust_codegen_supported(model: object) -> None:
    message = rust_codegen_error(model)
    if message is not None:
        raise GlyphError(message)


def build_analysis_rust_artifacts(model: CompilationModel) -> RustArtifacts:
    """Return safe Studio artifacts without pretending Assembly Rust exists."""

    if has_assemblies(model):
        return RustArtifacts(_BLOCKED_LOGIC, _BLOCKED_HOST, "")
    return _build_legacy_rust_artifacts(model)


def build_rust_artifacts(model: CompilationModel) -> RustArtifacts:
    require_rust_codegen_supported(model)
    return _build_legacy_rust_artifacts(model)


def compile_artifacts(source: str) -> RustArtifacts:
    model = parse_compilation_model(source)
    return build_rust_artifacts(model)


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


__all__ = [
    "AssemblyCompilationModel",
    "AssemblyExpandedCompilation",
    "build_analysis_rust_artifacts",
    "build_rust_artifacts",
    "compile_artifact_files",
    "compile_artifacts",
    "has_assemblies",
    "parse_artifact_model",
    "parse_compilation_model",
    "require_rust_codegen_supported",
    "rust_codegen_error",
]

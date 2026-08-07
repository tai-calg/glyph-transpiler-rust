from __future__ import annotations

from dataclasses import dataclass, fields, replace
from pathlib import Path

from .assembly import (
    AssemblyDecl,
    MachineAssemblyIR,
    _direct_calls,
    _value_expressions,
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
from .execution_ir import build_execution_structure_ir
from .machine import MachineDecl
from .state_machine_analysis import analyze_machine
from .state_transition_compiler import build_machine_state_transition_ir
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


def _operation_name(call: str) -> str:
    open_position = call.find("(")
    return call[:open_position].strip() if open_position > 0 else call.strip()


def _expand_inline_effect_chain(
    direct: set[str],
    base: CompilationModel,
) -> set[str]:
    """Expand only from normalized reachable transition operations.

    The normalized StateTransitionIR decides which operation call sites are real
    transition Actions. Inline effect prototypes may then delegate to another
    declared effect; that delegation remains part of the same Action chain.
    """

    functions = {
        item.name: item
        for item in base.program.declarations
        if isinstance(item, FunctionDecl)
    }
    externs = {
        item.name: item
        for item in base.program.declarations
        if isinstance(item, ExternDecl)
    }
    inline_effects = {item.name: item for item in base.inline_effects}
    result: set[str] = set()
    pending = list(direct)
    visited: set[str] = set()

    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        if name in externs:
            result.add(name)
            implementation = inline_effects.get(name)
            if implementation is not None:
                for expression in _value_expressions(implementation):
                    pending.extend(_direct_calls(expression))
            continue
        function = functions.get(name)
        if function is not None:
            for expression in _value_expressions(function):
                pending.extend(_direct_calls(expression))
    return result


def _normalized_machine_actions(
    base: CompilationModel,
    source_name: str,
) -> dict[str, set[str]]:
    """Use the existing normalized StateTransitionIR as the Action authority."""

    execution = build_execution_structure_ir(
        base.preprocess.source,
        source_name,
        base.program,
        base.specs,
        base.machines,
    )
    actions: dict[str, set[str]] = {}
    for machine_view in execution.machines:
        analyzed = analyze_machine(base, machine_view)
        normalized = build_machine_state_transition_ir(base, analyzed)
        direct: set[str] = set()
        for transition in normalized.get("transitions", []):
            if not bool(transition.get("source_reachable", True)):
                continue
            action = str(transition.get("action") or "").strip()
            if not action:
                continue
            direct.update(
                name
                for name in (
                    _operation_name(item)
                    for item in action.split("; ")
                )
                if name
            )
        actions[machine_view.name] = _expand_inline_effect_chain(direct, base)
    return actions


def _validate_route_sources_are_actions(
    base: CompilationModel,
    assemblies: tuple[AssemblyDecl, ...],
    actions_by_machine: dict[str, set[str]],
) -> None:
    """Reject guard-only, unreachable and state-unreachable route sources."""

    machines = {machine.name: machine for machine in base.machines}
    effects = {
        item.name
        for item in base.program.declarations
        if isinstance(item, ExternDecl)
    }

    for assembly in assemblies:
        instance_machines = {
            instance.name: machines.get(instance.machine)
            for instance in assembly.instances
        }
        for route in assembly.routes:
            machine = instance_machines.get(route.source_instance)
            if machine is None or route.effect not in effects:
                continue
            if route.effect not in actions_by_machine.get(machine.name, set()):
                raise GlyphError(
                    f"{route.line}行目: effect '{route.effect}' はMachine "
                    f"'{machine.name}' の到達可能な遷移Actionに存在しない"
                )


def _bind_normalized_actions(
    assembly_ir: tuple[MachineAssemblyIR, ...],
    actions_by_machine: dict[str, set[str]],
) -> tuple[MachineAssemblyIR, ...]:
    result: list[MachineAssemblyIR] = []
    for assembly in assembly_ir:
        instances = tuple(
            {
                **dict(instance),
                "allowed_effects": sorted(
                    actions_by_machine.get(str(instance["machine"]), set())
                ),
            }
            for instance in assembly.instances
        )
        result.append(replace(assembly, instances=instances))
    return tuple(result)


def parse_compilation_model(
    source: str,
    source_name: str = "input.glyph",
) -> CompilationModel:
    if not has_top_level_assembly(source):
        return _parse_legacy_compilation_model(source, source_name)

    parser_source, assemblies = extract_assemblies(source)
    base = _parse_legacy_compilation_model(parser_source, source_name)
    actions_by_machine = _normalized_machine_actions(base, source_name)
    _validate_route_sources_are_actions(base, assemblies, actions_by_machine)
    assembly_ir = validate_assemblies(
        base.program,
        base.machines,
        assemblies,
        base.inline_effects,
    )
    assembly_ir = _bind_normalized_actions(assembly_ir, actions_by_machine)

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

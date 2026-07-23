from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path

from .algorithm_ir import build_algorithm_ir
from .algorithm_mermaid import render_algorithm_mermaid
from .artifacts import CompilationModel, RustArtifacts, _generate_host, parse_compilation_model
from .execution_ir import build_execution_structure_ir
from .mermaid import DiagramBundle, _slug, _source_map, render_architecture_mermaid, render_dataflow_mermaid, render_index_markdown, render_machine_mermaid, render_temporal_mermaid
from .opaque import OpaqueAwareRustGenerator, generate_manual_scaffold
from .preprocessor import remap_source_lines
from .resource_flow import build_resource_flow
from .schema import ALGORITHM_IR_SCHEMA, EXECUTION_IR_SCHEMA, SOURCE_MAP_SCHEMA, TYPED_DESIGN_SCHEMA, versioned_payload
from .temporal_codegen import append_temporal_rust
from .temporal_stream_codegen import append_streaming_temporal_rust
from .temporal_stream_safety_codegen import append_safety_streaming_temporal_rust
from .verification import build_verification_report


@dataclass(frozen=True)
class CompilationOutputs:
    model: CompilationModel
    artifacts: RustArtifacts
    diagrams: DiagramBundle
    design_json: str


def _with_schema(schema: str, payload: dict[str, object]) -> dict[str, object]:
    if payload.get("schema") == schema and isinstance(payload.get("version"), int):
        return payload
    payload = dict(payload)
    payload.pop("schema", None)
    payload.pop("version", None)
    return versioned_payload(schema, payload)


def _has_contracts(model: CompilationModel) -> bool:
    return bool(model.contracts.declarations or model.contracts.applications)


def _has_capabilities(model: CompilationModel) -> bool:
    return bool(model.capabilities.resources or model.capabilities.functions or model.capabilities.aggregates or model.capabilities.operations)


def _has_runtime_contracts(model: CompilationModel) -> bool:
    return bool(model.runtime_contracts.worlds or model.runtime_contracts.protocols or model.runtime_contracts.handlers or model.runtime_contracts.laws or model.runtime_contracts.applications)


def _has_glyph04(model: CompilationModel) -> bool:
    return _has_capabilities(model) or _has_contracts(model) or _has_runtime_contracts(model)


def build_rust_artifacts(model: CompilationModel) -> RustArtifacts:
    logic = append_temporal_rust(OpaqueAwareRustGenerator(model.program, model.opaques, model.blocks).generate(), model.program, model.specs)
    logic = append_streaming_temporal_rust(logic, model.program, model.specs)
    logic = append_safety_streaming_temporal_rust(logic, model.program, model.specs)
    return RustArtifacts(logic=logic, host=_generate_host(model.program, model.inline_effects, model.opaques), manual_scaffold=generate_manual_scaffold(model.program, model.opaques))


def build_design_json(model: CompilationModel) -> str:
    semantic = model.semantic.to_dict()
    semantic.pop("schema", None)
    semantic.pop("version", None)
    payload = versioned_payload(TYPED_DESIGN_SCHEMA, semantic)
    payload["raw_macros"] = [item.to_dict() for item in model.preprocess.macros]
    payload["preprocessor"] = {"schema": "glyph.preprocessor", "version": 1, "changed": model.preprocess.changed, "expanded_line_count": len(model.preprocess.lines)}
    payload["blocks"] = [item.to_dict() for item in model.blocks]
    payload["lambdas"] = [asdict(item) for item in model.lambdas]
    payload["architecture"] = model.architecture.to_dict()
    payload["rust_todos"] = [item.to_dict() for item in model.opaques]
    if _has_capabilities(model):
        payload["capabilities"] = model.capabilities.to_dict()
        payload["resource_flow"] = build_resource_flow(model.capabilities).to_dict()
    if _has_contracts(model):
        payload["contracts"] = model.contracts.to_dict()
    if _has_runtime_contracts(model):
        payload["runtime_contracts"] = model.runtime_contracts.to_dict()
    if _has_glyph04(model):
        payload["verification"] = build_verification_report(model.capabilities, model.runtime_contracts).to_dict()
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def build_diagram_bundle(model: CompilationModel, source_name: str, source_href: str | None = None) -> DiagramBundle:
    expanded = model.expanded
    ir = build_execution_structure_ir(model.preprocess.source, source_name, expanded.program, expanded.specs, expanded.machines)
    ir = remap_source_lines(ir, model.preprocess)
    algorithm_ir = build_algorithm_ir(model.preprocess.source, source_name, expanded.program, expanded.blocks, expanded.lambdas, expanded.opaques)
    algorithm_ir = remap_source_lines(algorithm_ir, model.preprocess)

    href = source_href or source_name
    architecture = render_architecture_mermaid(model.architecture, href)
    logic = render_algorithm_mermaid(algorithm_ir, href)
    dataflow = render_dataflow_mermaid(ir, href)
    machine_files = {f"machine-{_slug(machine.name)}.mmd": render_machine_mermaid(machine) for machine in ir.machines}
    temporal = render_temporal_mermaid(ir, href)

    files = {
        "preprocessed.glyph": model.preprocess.source,
        "preprocessor-map.json": json.dumps(model.preprocess.map_dict(source_name), ensure_ascii=False, indent=2) + "\n",
        "architecture.mmd": architecture,
        "architecture-ir.json": json.dumps(model.architecture.to_dict(), ensure_ascii=False, indent=2) + "\n",
        "logic.mmd": logic,
        "algorithm-ir.json": json.dumps(_with_schema(ALGORITHM_IR_SCHEMA, algorithm_ir.to_dict()), ensure_ascii=False, indent=2) + "\n",
        "execution.mmd": dataflow,
        **machine_files,
        "temporal.mmd": temporal,
        "execution-ir.json": json.dumps(_with_schema(EXECUTION_IR_SCHEMA, ir.to_dict()), ensure_ascii=False, indent=2) + "\n",
        "source-map.json": json.dumps(_with_schema(SOURCE_MAP_SCHEMA, _source_map(ir, model.architecture, algorithm_ir)), ensure_ascii=False, indent=2) + "\n",
    }
    if _has_capabilities(model):
        files["capability-ir.json"] = json.dumps(model.capabilities.to_dict(), ensure_ascii=False, indent=2) + "\n"
        files["resource-flow-ir.json"] = json.dumps(build_resource_flow(model.capabilities).to_dict(), ensure_ascii=False, indent=2) + "\n"
    if _has_contracts(model):
        files["contracts-ir.json"] = json.dumps(model.contracts.to_dict(), ensure_ascii=False, indent=2) + "\n"
    if _has_runtime_contracts(model):
        files["runtime-contract-ir.json"] = json.dumps(model.runtime_contracts.to_dict(), ensure_ascii=False, indent=2) + "\n"
    if _has_glyph04(model):
        files["verification-report.json"] = json.dumps(build_verification_report(model.capabilities, model.runtime_contracts).to_dict(), ensure_ascii=False, indent=2) + "\n"
    files["index.md"] = render_index_markdown(ir, model.architecture, algorithm_ir, href, architecture, logic, dataflow, machine_files, temporal)
    return DiagramBundle(ir=ir, algorithm_ir=algorithm_ir, files=files)


class CompilationPipeline:
    def compile_text(self, source: str, source_name: str = "input.glyph", source_href: str | None = None) -> CompilationOutputs:
        model = parse_compilation_model(source, source_name)
        return CompilationOutputs(model=model, artifacts=build_rust_artifacts(model), diagrams=build_diagram_bundle(model, source_name, source_href), design_json=build_design_json(model))


def compile_outputs(source: str, source_name: str = "input.glyph", source_href: str | None = None) -> CompilationOutputs:
    return CompilationPipeline().compile_text(source, source_name, source_href)


def compile_diagram_bundle(source: str, source_name: str = "input.glyph", source_href: str | None = None) -> DiagramBundle:
    return compile_outputs(source, source_name, source_href).diagrams


def write_diagram_bundle(input_path: str | Path, output_dir: str | Path) -> DiagramBundle:
    input_file = Path(input_path)
    destination = Path(output_dir)
    source = input_file.read_text(encoding="utf-8")
    source_href = os.path.relpath(input_file, destination).replace(os.sep, "/")
    bundle = compile_diagram_bundle(source, str(input_file), source_href)
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in bundle.files.items():
        (destination / name).write_text(content, encoding="utf-8")
    return bundle

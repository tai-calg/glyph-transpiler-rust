from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path

from .algorithm_ir import build_algorithm_ir
from .algorithm_mermaid import render_algorithm_mermaid
from .artifacts import (
    CompilationModel,
    RustArtifacts,
    _generate_host,
    parse_compilation_model,
)
from .execution_ir import build_execution_structure_ir
from .mermaid import (
    DiagramBundle,
    _slug,
    _source_map,
    render_architecture_mermaid,
    render_dataflow_mermaid,
    render_index_markdown,
    render_machine_mermaid,
    render_temporal_mermaid,
)
from .opaque import OpaqueAwareRustGenerator, generate_manual_scaffold
from .preprocessor import remap_source_lines
from .schema import (
    ALGORITHM_IR_SCHEMA,
    EXECUTION_IR_SCHEMA,
    SOURCE_MAP_SCHEMA,
    TYPED_DESIGN_SCHEMA,
    versioned_payload,
)
from .temporal_codegen import append_temporal_rust
from .temporal_stream_codegen import append_streaming_temporal_rust
from .temporal_stream_safety_codegen import append_safety_streaming_temporal_rust


@dataclass(frozen=True)
class CompilationOutputs:
    """All deterministic outputs derived from one shared CompilationModel."""

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


def build_rust_artifacts(model: CompilationModel) -> RustArtifacts:
    """Generate Rust from an already parsed and validated model."""

    logic = append_temporal_rust(
        OpaqueAwareRustGenerator(
            model.program,
            model.opaques,
            model.blocks,
        ).generate(),
        model.program,
        model.specs,
    )
    logic = append_streaming_temporal_rust(logic, model.program, model.specs)
    logic = append_safety_streaming_temporal_rust(
        logic,
        model.program,
        model.specs,
    )
    return RustArtifacts(
        logic=logic,
        host=_generate_host(model.program, model.inline_effects, model.opaques),
        manual_scaffold=generate_manual_scaffold(model.program, model.opaques),
    )


def build_design_json(model: CompilationModel) -> str:
    """Serialize the complete typed design contract with an explicit schema version."""

    semantic = model.semantic.to_dict()
    semantic.pop("schema", None)
    semantic.pop("version", None)
    payload = versioned_payload(TYPED_DESIGN_SCHEMA, semantic)
    payload["raw_macros"] = [item.to_dict() for item in model.preprocess.macros]
    payload["preprocessor"] = {
        "schema": "glyph.preprocessor",
        "version": 1,
        "changed": model.preprocess.changed,
        "expanded_line_count": len(model.preprocess.lines),
    }
    payload["blocks"] = [item.to_dict() for item in model.blocks]
    payload["lambdas"] = [asdict(item) for item in model.lambdas]
    payload["architecture"] = model.architecture.to_dict()
    payload["rust_todos"] = [item.to_dict() for item in model.opaques]
    if _has_contracts(model):
        payload["contracts"] = model.contracts.to_dict()
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def build_diagram_bundle(
    model: CompilationModel,
    source_name: str,
    source_href: str | None = None,
) -> DiagramBundle:
    """Build all IR and diagram artifacts without reparsing the source."""

    expanded = model.expanded
    ir = build_execution_structure_ir(
        model.preprocess.source,
        source_name,
        expanded.program,
        expanded.specs,
        expanded.machines,
    )
    ir = remap_source_lines(ir, model.preprocess)
    algorithm_ir = build_algorithm_ir(
        model.preprocess.source,
        source_name,
        expanded.program,
        expanded.blocks,
        expanded.lambdas,
        expanded.opaques,
    )
    algorithm_ir = remap_source_lines(algorithm_ir, model.preprocess)

    href = source_href or source_name
    architecture = render_architecture_mermaid(model.architecture, href)
    logic = render_algorithm_mermaid(algorithm_ir, href)
    dataflow = render_dataflow_mermaid(ir, href)
    machine_files = {
        f"machine-{_slug(machine.name)}.mmd": render_machine_mermaid(machine)
        for machine in ir.machines
    }
    temporal = render_temporal_mermaid(ir, href)

    architecture_payload = model.architecture.to_dict()
    algorithm_payload = _with_schema(ALGORITHM_IR_SCHEMA, algorithm_ir.to_dict())
    execution_payload = _with_schema(EXECUTION_IR_SCHEMA, ir.to_dict())
    source_map_payload = _with_schema(
        SOURCE_MAP_SCHEMA,
        _source_map(ir, model.architecture, algorithm_ir),
    )

    files = {
        "preprocessed.glyph": model.preprocess.source,
        "preprocessor-map.json": json.dumps(
            model.preprocess.map_dict(source_name),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "architecture.mmd": architecture,
        "architecture-ir.json": json.dumps(
            architecture_payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "logic.mmd": logic,
        "algorithm-ir.json": json.dumps(
            algorithm_payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "execution.mmd": dataflow,
        **machine_files,
        "temporal.mmd": temporal,
        "execution-ir.json": json.dumps(
            execution_payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "source-map.json": json.dumps(
            source_map_payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    }
    if _has_contracts(model):
        files["contracts-ir.json"] = json.dumps(
            model.contracts.to_dict(),
            ensure_ascii=False,
            indent=2,
        ) + "\n"
    files["index.md"] = render_index_markdown(
        ir,
        model.architecture,
        algorithm_ir,
        href,
        architecture,
        logic,
        dataflow,
        machine_files,
        temporal,
    )
    return DiagramBundle(ir=ir, algorithm_ir=algorithm_ir, files=files)


class CompilationPipeline:
    """Authoritative source -> model -> Rust/IR/JSON pipeline.

    Compatibility entry points return subsets of these outputs. Studio, watch mode, the
    CLI, and external integrations use this class so parsing and validation happen exactly
    once per source digest.
    """

    def compile_text(
        self,
        source: str,
        source_name: str = "input.glyph",
        source_href: str | None = None,
    ) -> CompilationOutputs:
        model = parse_compilation_model(source, source_name)
        return CompilationOutputs(
            model=model,
            artifacts=build_rust_artifacts(model),
            diagrams=build_diagram_bundle(model, source_name, source_href),
            design_json=build_design_json(model),
        )


def compile_outputs(
    source: str,
    source_name: str = "input.glyph",
    source_href: str | None = None,
) -> CompilationOutputs:
    """Functional entry point for the authoritative compilation pipeline."""

    return CompilationPipeline().compile_text(source, source_name, source_href)


def compile_diagram_bundle(
    source: str,
    source_name: str = "input.glyph",
    source_href: str | None = None,
) -> DiagramBundle:
    """Compatibility API backed by the authoritative single-pass pipeline."""

    return compile_outputs(source, source_name, source_href).diagrams


def write_diagram_bundle(
    input_path: str | Path,
    output_dir: str | Path,
) -> DiagramBundle:
    """Compile and write versioned IR/diagram artifacts through one pipeline run."""

    input_file = Path(input_path)
    destination = Path(output_dir)
    source = input_file.read_text(encoding="utf-8")
    source_href = os.path.relpath(input_file, destination).replace(os.sep, "/")
    bundle = compile_diagram_bundle(source, str(input_file), source_href)
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in bundle.files.items():
        (destination / name).write_text(content, encoding="utf-8")
    return bundle

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
    build_rust_artifacts,
    parse_compilation_model,
)
from .execution_ir import build_execution_structure_ir
from .glyph04_derived import Glyph04DerivedModels, derive_glyph04_models
from .host_binding_codegen import render_host_binding_trait
from .host_requirements import HostRequirementModel
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
from .preprocessor import remap_source_lines
from .schema import (
    ALGORITHM_IR_SCHEMA,
    EXECUTION_IR_SCHEMA,
    SOURCE_MAP_SCHEMA,
    TYPED_DESIGN_SCHEMA,
    versioned_payload,
)


@dataclass(frozen=True)
class CompilationOutputs:
    model: CompilationModel
    artifacts: RustArtifacts
    diagrams: DiagramBundle
    design_json: str


def _with_schema(schema: str, payload: dict[str, object]) -> dict[str, object]:
    if payload.get("schema") == schema and isinstance(payload.get("version"), int):
        return payload
    unversioned = dict(payload)
    unversioned.pop("schema", None)
    unversioned.pop("version", None)
    return versioned_payload(schema, unversioned)


def _derive(model: CompilationModel) -> Glyph04DerivedModels:
    return derive_glyph04_models(
        model.capabilities,
        model.contracts,
        model.runtime_contracts,
    )


def build_host_requirement_model(model: CompilationModel) -> HostRequirementModel:
    """Compatibility facade for tooling that requests only Host requirements."""

    return _derive(model).host_requirements


def build_design_json(
    model: CompilationModel,
    derived: Glyph04DerivedModels | None = None,
) -> str:
    derived = derived or _derive(model)
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

    if derived.features.capabilities:
        payload["capabilities"] = model.capabilities.to_dict()
        payload["resource_flow"] = derived.resource_flow.to_dict()
    if derived.features.contracts:
        payload["contracts"] = model.contracts.to_dict()
    if derived.features.runtime_contracts:
        payload["runtime_contracts"] = model.runtime_contracts.to_dict()
    if derived.features.enabled:
        payload["verification"] = derived.verification.to_dict()
        payload["host_requirements"] = derived.host_requirements.to_dict()
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def build_diagram_bundle(
    model: CompilationModel,
    source_name: str,
    source_href: str | None = None,
    derived: Glyph04DerivedModels | None = None,
) -> DiagramBundle:
    derived = derived or _derive(model)
    expanded = model.expanded
    execution_ir = build_execution_structure_ir(
        model.preprocess.source,
        source_name,
        expanded.program,
        expanded.specs,
        expanded.machines,
    )
    execution_ir = remap_source_lines(execution_ir, model.preprocess)
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
    dataflow = render_dataflow_mermaid(execution_ir, href)
    machine_files = {
        f"machine-{_slug(machine.name)}.mmd": render_machine_mermaid(machine)
        for machine in execution_ir.machines
    }
    temporal = render_temporal_mermaid(execution_ir, href)

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
            model.architecture.to_dict(),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "logic.mmd": logic,
        "algorithm-ir.json": json.dumps(
            _with_schema(ALGORITHM_IR_SCHEMA, algorithm_ir.to_dict()),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "execution.mmd": dataflow,
        **machine_files,
        "temporal.mmd": temporal,
        "execution-ir.json": json.dumps(
            _with_schema(EXECUTION_IR_SCHEMA, execution_ir.to_dict()),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "source-map.json": json.dumps(
            _with_schema(
                SOURCE_MAP_SCHEMA,
                _source_map(execution_ir, model.architecture, algorithm_ir),
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    }

    if derived.features.capabilities:
        files["capability-ir.json"] = json.dumps(
            model.capabilities.to_dict(),
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        files["resource-flow-ir.json"] = json.dumps(
            derived.resource_flow.to_dict(),
            ensure_ascii=False,
            indent=2,
        ) + "\n"
    if derived.features.contracts:
        files["contracts-ir.json"] = json.dumps(
            model.contracts.to_dict(),
            ensure_ascii=False,
            indent=2,
        ) + "\n"
    if derived.features.runtime_contracts:
        files["runtime-contract-ir.json"] = json.dumps(
            model.runtime_contracts.to_dict(),
            ensure_ascii=False,
            indent=2,
        ) + "\n"
    if derived.features.enabled:
        files["verification-report.json"] = json.dumps(
            derived.verification.to_dict(),
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        files["host-requirements-ir.json"] = json.dumps(
            derived.host_requirements.to_dict(),
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        files["host-binding.generated.rs"] = render_host_binding_trait(
            derived.host_requirements
        )

    files["index.md"] = render_index_markdown(
        execution_ir,
        model.architecture,
        algorithm_ir,
        href,
        architecture,
        logic,
        dataflow,
        machine_files,
        temporal,
    )
    return DiagramBundle(
        ir=execution_ir,
        algorithm_ir=algorithm_ir,
        files=files,
    )


class CompilationPipeline:
    def compile_text(
        self,
        source: str,
        source_name: str = "input.glyph",
        source_href: str | None = None,
    ) -> CompilationOutputs:
        model = parse_compilation_model(source, source_name)
        derived = _derive(model)
        return CompilationOutputs(
            model=model,
            artifacts=build_rust_artifacts(model),
            diagrams=build_diagram_bundle(
                model,
                source_name,
                source_href,
                derived,
            ),
            design_json=build_design_json(model, derived),
        )


def compile_outputs(
    source: str,
    source_name: str = "input.glyph",
    source_href: str | None = None,
) -> CompilationOutputs:
    return CompilationPipeline().compile_text(source, source_name, source_href)


def compile_diagram_bundle(
    source: str,
    source_name: str = "input.glyph",
    source_href: str | None = None,
) -> DiagramBundle:
    return compile_outputs(source, source_name, source_href).diagrams


def write_diagram_bundle(
    input_path: str | Path,
    output_dir: str | Path,
) -> DiagramBundle:
    input_file = Path(input_path)
    destination = Path(output_dir)
    source = input_file.read_text(encoding="utf-8")
    source_href = os.path.relpath(input_file, destination).replace(os.sep, "/")
    bundle = compile_diagram_bundle(source, str(input_file), source_href)
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in bundle.files.items():
        (destination / name).write_text(content, encoding="utf-8")
    return bundle

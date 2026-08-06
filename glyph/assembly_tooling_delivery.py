from __future__ import annotations

import json
import re

from .assembly_delivery import _patch_function_references


_RUNTIME_CODEGEN_MESSAGE = (
    "Glyph Machine Assembly immediate routing has not yet been lowered into "
    "generated Rust; use machine-assembly-ir.json and the reference runtime"
)


def _assembly_irs(model) -> tuple[object, ...]:
    value = getattr(model, "assembly_ir", ())
    return tuple(value) if value else ()


def machine_assembly_payload(model) -> dict[str, object]:
    return {
        "schema": "glyph.machine-assembly-set-ir",
        "version": 1,
        "runtime_codegen": {
            "status": "not-lowered",
            "fail_closed": True,
        },
        "assemblies": [item.to_dict() for item in _assembly_irs(model)],
    }


def _mermaid_id(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", text)
    return cleaned or "assembly"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def render_machine_assembly_mermaid(model) -> str:
    lines = [
        "flowchart LR",
        "  classDef machine fill:#eef,stroke:#446;",
    ]
    for assembly_index, assembly in enumerate(_assembly_irs(model), start=1):
        assembly_id = f"assembly_{assembly_index}_{_mermaid_id(assembly.name)}"
        lines.append(f'  subgraph {assembly_id}["{_escape(assembly.name)}"]')
        node_ids: dict[str, str] = {}
        for instance_index, instance in enumerate(assembly.instances, start=1):
            instance_name = str(instance["name"])
            node_id = (
                f"{assembly_id}_instance_{instance_index}_"
                f"{_mermaid_id(instance_name)}"
            )
            node_ids[instance_name] = node_id
            label = f"{instance_name}: {instance['machine']}"
            lines.append(f'    {node_id}["{_escape(label)}"]')
            lines.append(f"    class {node_id} machine;")
        for route in assembly.routes:
            source = node_ids[str(route["source_instance"])]
            target = node_ids[str(route["target_instance"])]
            label = f"{route['effect']} → {route['input']}"
            lines.append(f'    {source} -->|"{_escape(label)}"| {target}')
        lines.append("  end")
    return "\n".join(lines) + "\n"


def install_machine_assembly_tooling_delivery() -> None:
    """Publish opt-in Assembly artifacts and fail closed in legacy Rust codegen."""

    from . import artifacts as artifacts_module
    from . import compilation as compilation_module

    current_rust = artifacts_module.build_rust_artifacts
    if not getattr(current_rust, "__glyph_machine_assembly__", False):
        original_rust = current_rust

        def build_rust_artifacts_with_assembly_guard(model):
            artifacts = original_rust(model)
            if not _assembly_irs(model):
                return artifacts
            logic = artifacts.logic.rstrip() + (
                "\n\ncompile_error!(\""
                + _RUNTIME_CODEGEN_MESSAGE
                + "\");\n"
            )
            return type(artifacts)(logic, artifacts.host, artifacts.manual_scaffold)

        build_rust_artifacts_with_assembly_guard.__name__ = original_rust.__name__
        build_rust_artifacts_with_assembly_guard.__qualname__ = original_rust.__qualname__
        build_rust_artifacts_with_assembly_guard.__doc__ = original_rust.__doc__
        build_rust_artifacts_with_assembly_guard.__glyph_machine_assembly__ = True
        build_rust_artifacts_with_assembly_guard.__glyph_original__ = original_rust
        _patch_function_references(original_rust, build_rust_artifacts_with_assembly_guard)
        artifacts_module.build_rust_artifacts = build_rust_artifacts_with_assembly_guard

    current_design = compilation_module.build_design_json
    if not getattr(current_design, "__glyph_machine_assembly__", False):
        original_design = current_design

        def build_design_json_with_assemblies(model, derived=None):
            rendered = original_design(model, derived)
            if not _assembly_irs(model):
                return rendered
            payload = json.loads(rendered)
            payload["machine_assemblies"] = machine_assembly_payload(model)
            return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

        build_design_json_with_assemblies.__name__ = original_design.__name__
        build_design_json_with_assemblies.__qualname__ = original_design.__qualname__
        build_design_json_with_assemblies.__doc__ = original_design.__doc__
        build_design_json_with_assemblies.__glyph_machine_assembly__ = True
        build_design_json_with_assemblies.__glyph_original__ = original_design
        _patch_function_references(original_design, build_design_json_with_assemblies)
        compilation_module.build_design_json = build_design_json_with_assemblies

    current_bundle = compilation_module.build_diagram_bundle
    if not getattr(current_bundle, "__glyph_machine_assembly__", False):
        original_bundle = current_bundle

        def build_diagram_bundle_with_assemblies(
            model,
            source_name,
            source_href=None,
            derived=None,
        ):
            bundle = original_bundle(model, source_name, source_href, derived)
            if not _assembly_irs(model):
                return bundle
            files = dict(bundle.files)
            files["machine-assembly-ir.json"] = json.dumps(
                machine_assembly_payload(model),
                ensure_ascii=False,
                indent=2,
            ) + "\n"
            files["machine-assembly.mmd"] = render_machine_assembly_mermaid(model)
            return type(bundle)(bundle.ir, bundle.algorithm_ir, files)

        build_diagram_bundle_with_assemblies.__name__ = original_bundle.__name__
        build_diagram_bundle_with_assemblies.__qualname__ = original_bundle.__qualname__
        build_diagram_bundle_with_assemblies.__doc__ = original_bundle.__doc__
        build_diagram_bundle_with_assemblies.__glyph_machine_assembly__ = True
        build_diagram_bundle_with_assemblies.__glyph_original__ = original_bundle
        _patch_function_references(original_bundle, build_diagram_bundle_with_assemblies)
        compilation_module.build_diagram_bundle = build_diagram_bundle_with_assemblies

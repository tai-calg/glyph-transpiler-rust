from __future__ import annotations

import json
import re
from typing import Mapping


def _assembly_irs(model) -> tuple[object, ...]:
    value = getattr(model, "assembly_ir", ())
    return tuple(value) if value else ()


def machine_assembly_payload(model) -> dict[str, object]:
    return {
        "schema": "glyph.machine-assembly-set-ir",
        "version": 2,
        "runtime_codegen": {
            "status": "blocked",
            "reason": "instance-aware-rust-lowering-not-implemented",
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
        "  classDef host fill:#fee,stroke:#844,stroke-dasharray:4 3;",
    ]
    for assembly_index, assembly in enumerate(_assembly_irs(model), start=1):
        assembly_id = f"assembly_{assembly_index}_{_mermaid_id(assembly.name)}"
        lines.append(f'  subgraph {assembly_id}["{_escape(assembly.name)}"]')
        node_ids: dict[str, str] = {}
        routed: dict[str, set[str]] = {}
        for route in assembly.routes:
            routed.setdefault(str(route["source_instance"]), set()).add(
                str(route["effect"])
            )

        for instance_index, instance in enumerate(assembly.instances, start=1):
            instance_name = str(instance["name"])
            node_id = (
                f"{assembly_id}_instance_{instance_index}_"
                f"{_mermaid_id(instance_name)}"
            )
            node_ids[instance_name] = node_id
            input_names = [
                f"{item.get('name')}:{item.get('type')}"
                for item in instance.get("inputs", ())
                if isinstance(item, Mapping)
            ]
            suffix = f"<br/>in: {', '.join(input_names)}" if input_names else ""
            label = f"{instance_name}: {instance['machine']}{suffix}"
            lines.append(f'    {node_id}["{_escape(label)}"]')
            lines.append(f"    class {node_id} machine;")

        host_id = f"{assembly_id}_host"
        host_used = False
        for route in assembly.routes:
            source = node_ids[str(route["source_instance"])]
            target = node_ids[str(route["target_instance"])]
            label = (
                f"{route['effect']}({route['payload_parameter']}:"
                f"{route['payload_type']}) → {route['input']}"
            )
            lines.append(f'    {source} -->|"{_escape(label)}"| {target}')

        for instance in assembly.instances:
            instance_name = str(instance["name"])
            for effect in instance.get("allowed_effects", ()):
                effect_name = str(effect)
                if effect_name in routed.get(instance_name, set()):
                    continue
                if not host_used:
                    lines.append(f'    {host_id}[/"Host effects"/]')
                    lines.append(f"    class {host_id} host;")
                    host_used = True
                lines.append(
                    f'    {node_ids[instance_name]} -.->|"{_escape(effect_name)}"| {host_id}'
                )
        lines.append("  end")
    return "\n".join(lines) + "\n"



__all__ = [
    "machine_assembly_payload",
    "render_machine_assembly_mermaid",
]

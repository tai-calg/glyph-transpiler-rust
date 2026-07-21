from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

from .algorithm_ir import AlgorithmIR, build_algorithm_ir
from .algorithm_mermaid import algorithm_source_entries, render_algorithm_mermaid
from .architecture import ArchitectureIR
from .artifacts import parse_compilation_model
from .execution_ir import ExecutionStructureIR, build_execution_structure_ir


@dataclass(frozen=True)
class DiagramBundle:
    ir: ExecutionStructureIR
    algorithm_ir: AlgorithmIR
    files: dict[str, str]


def _slug(text: str) -> str:
    value = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    return "-".join(part for part in value.split("-") if part) or "machine"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "<br/>")


def _source_url(source_href: str, line: int) -> str:
    return f"{source_href}#L{line}"


def render_architecture_mermaid(
    architecture: ArchitectureIR, source_href: str
) -> str:
    lines = [
        "flowchart LR",
        "  classDef function fill:#eef,stroke:#446;",
        "  classDef effect fill:#fee,stroke:#844;",
        "  classDef rust fill:#f4e5ff,stroke:#8050a0;",
        "  classDef data fill:#efe,stroke:#484;",
        "  classDef external fill:#f7f7f7,stroke:#777,stroke-dasharray: 4 3;",
    ]
    for system in architecture.systems:
        lines.append(f'  subgraph {system.id}["{_escape(system.name)}"]')
        for component in system.components:
            label = _escape(
                f"{component.name}<br/>{component.kind} [L{component.line}]"
            )
            if component.kind == "effect":
                lines.append(f'    {component.id}[/"{label}"/]')
            elif component.kind == "data":
                lines.append(f'    {component.id}[("{label}")]')
            else:
                lines.append(f'    {component.id}["{label}"]')
            lines.append(f"    class {component.id} {component.kind};")
            lines.append(
                f'    click {component.id} "{_source_url(source_href, component.line)}" '
                f'"Open {architecture.source_name}:{component.line}"'
            )
        for edge in system.edges:
            lines.append(f"    {edge.source_id} --> {edge.target_id}")
        lines.append("  end")
    return "\n".join(lines) + "\n"


def render_dataflow_mermaid(ir: ExecutionStructureIR, source_href: str) -> str:
    lines = [
        "flowchart TD",
        "  classDef function fill:#eef,stroke:#446;",
        "  classDef effect fill:#fee,stroke:#844;",
        "  classDef decision fill:#ffd,stroke:#884;",
        "  classDef error fill:#fdd,stroke:#a33;",
        "  classDef result fill:#efe,stroke:#484;",
    ]
    node_ids = {node.id for node in ir.nodes}
    for node in ir.nodes:
        label = _escape(f"{node.label} [L{node.source.line}]")
        if node.kind == "decision":
            definition = f'  {node.id}{{"{label}"}}'
        elif node.kind == "effect":
            definition = f'  {node.id}[/"{label}"/]'
        elif node.kind == "error":
            definition = f'  {node.id}(["{label}"])'
        else:
            definition = f'  {node.id}["{label}"]'
        lines.append(definition)
        lines.append(f"  class {node.id} {node.kind};")
        lines.append(
            f'  click {node.id} "{_source_url(source_href, node.source.line)}" '
            f'"Open {ir.source_name}:{node.source.line}"'
        )

    for edge in ir.edges:
        if edge.source_id not in node_ids or edge.target_id not in node_ids:
            continue
        label = _escape(edge.label)
        connector = f' -->|"{label}"| ' if label else " --> "
        lines.append(f"  {edge.source_id}{connector}{edge.target_id}")
    return "\n".join(lines) + "\n"


def render_machine_mermaid(machine) -> str:
    lines = ["stateDiagram-v2", "  direction LR"]
    state_names = {state.name for state in machine.states}
    for state in machine.states:
        lines.append(f'  state "{_escape(state.name)}" as {state.name}')
    lines.append(f"  [*] --> {machine.initial_state}: init")

    if any(
        transition.source_state == "*" or transition.target_state == "*"
        for transition in machine.transitions
    ):
        lines.append('  state "Any state" as __ANY__')

    for transition in machine.transitions:
        source = "__ANY__" if transition.source_state == "*" else transition.source_state
        target = "__ANY__" if transition.target_state == "*" else transition.target_state
        if source not in state_names and source != "__ANY__":
            continue
        if target not in state_names and target != "__ANY__":
            continue
        label = _escape(f"{transition.condition} [L{transition.source.line}]")
        lines.append(f"  {source} --> {target}: {label}")

    lines.append(f"  {machine.success_state} --> [*]: success")
    lines.append(f"  {machine.failure_state} --> [*]: failure")
    return "\n".join(lines) + "\n"


def render_temporal_mermaid(ir: ExecutionStructureIR, source_href: str) -> str:
    lines = [
        "flowchart LR",
        '  observations["Observation stream + at_ms"]',
        '  verdict["Satisfied / Pending / Violated"]',
    ]
    for item in ir.temporal:
        node_id = f"temporal_{_slug(item.name).replace('-', '_')}"
        label = _escape(f"{item.name}<br/>{item.formula} [L{item.source.line}]")
        lines.append(f'  {node_id}["{label}"]')
        lines.append(f"  observations --> {node_id}")
        lines.append(f"  {node_id} --> verdict")
        lines.append(
            f'  click {node_id} "{_source_url(source_href, item.source.line)}" '
            f'"Open {ir.source_name}:{item.source.line}"'
        )
    return "\n".join(lines) + "\n"


def _source_map(
    ir: ExecutionStructureIR,
    architecture: ArchitectureIR,
    algorithm_ir: AlgorithmIR,
) -> dict[str, object]:
    lines: dict[str, list[dict[str, str]]] = {}

    def add(line: int, kind: str, item_id: str, diagram: str) -> None:
        lines.setdefault(str(line), []).append(
            {"kind": kind, "id": item_id, "diagram": diagram}
        )

    for system in architecture.systems:
        add(system.line, "architecture-system", system.name, "architecture.mmd")
        for component in system.components:
            add(
                component.line,
                "architecture-component",
                component.name,
                "architecture.mmd",
            )
        for edge in system.edges:
            add(
                edge.line,
                "architecture-edge",
                f"{edge.source_id}->{edge.target_id}",
                "architecture.mmd",
            )
    for line, kind, item_id in algorithm_source_entries(algorithm_ir):
        add(line, kind, item_id, "logic.mmd")
    for node in ir.nodes:
        add(node.source.line, "execution-node", node.id, "execution.mmd")
    for machine in ir.machines:
        diagram = f"machine-{_slug(machine.name)}.mmd"
        add(machine.source.line, "machine", machine.name, diagram)
        for transition in machine.transitions:
            add(
                transition.source.line,
                "machine-transition",
                f"{transition.source_state}->{transition.target_state}",
                diagram,
            )
    for item in ir.temporal:
        add(item.source.line, "temporal", item.name, "temporal.mmd")
    return {"source": ir.source_name, "line_to_views": lines}


def render_index_markdown(
    ir: ExecutionStructureIR,
    architecture_ir: ArchitectureIR,
    algorithm_ir: AlgorithmIR,
    source_href: str,
    architecture: str,
    logic: str,
    dataflow: str,
    machines: dict[str, str],
    temporal: str,
) -> str:
    lines = [
        "# Glyph design views",
        "",
        f"Source: [`{ir.source_name}`]({_source_url(source_href, 1)})",
        "",
    ]
    if architecture_ir.systems:
        lines.extend(
            [
                "## Architecture",
                "",
                "```mermaid",
                architecture.rstrip(),
                "```",
                "",
            ]
        )
    if algorithm_ir.functions:
        lines.extend(
            [
                "## Source-level logic",
                "",
                "The diagram below is built from `:=`, guards, `/>`, lambdas, `~`, and `!` before compiler lowering.",
                "",
                "```mermaid",
                logic.rstrip(),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Lowered execution dataflow",
            "",
            "```mermaid",
            dataflow.rstrip(),
            "```",
            "",
        ]
    )
    for machine in ir.machines:
        filename = f"machine-{_slug(machine.name)}.mmd"
        lines.extend(
            [
                f"## Machine: {machine.name}",
                "",
                f"- state type: `{machine.state_type}`",
                f"- selector: `{machine.selector}`",
                f"- initial: `{machine.initial_state}`",
                f"- next: `{machine.next_function}`",
                f"- success: `{machine.success_state}`",
                f"- failure: `{machine.failure_state}`",
                "",
                "```mermaid",
                machines[filename].rstrip(),
                "```",
                "",
            ]
        )

    if ir.temporal:
        lines.extend(
            [
                "## Temporal constraints",
                "",
                "```mermaid",
                temporal.rstrip(),
                "```",
                "",
                "| Name | Formula | Reference | Streaming | Source |",
                "|---|---|---|---|---|",
            ]
        )
        for item in ir.temporal:
            source = f"[{item.source.line}]({_source_url(source_href, item.source.line)})"
            lines.append(
                f"| `{item.name}` | `{item.formula}` | `{item.reference_monitor}` | "
                f"`{item.streaming_monitor}` | {source} |"
            )
        lines.append("")

    source_map = _source_map(ir, architecture_ir, algorithm_ir)["line_to_views"]
    lines.extend(
        [
            "## Source map",
            "",
            "This table is the reverse index from source lines to generated views.",
            "",
            "| Source line | View items |",
            "|---:|---|",
        ]
    )
    assert isinstance(source_map, dict)
    for line in sorted(source_map, key=int):
        items = source_map[line]
        assert isinstance(items, list)
        rendered = ", ".join(
            f"`{item['kind']}:{item['id']}` → [{item['diagram']}]({item['diagram']})"
            for item in items
        )
        lines.append(f"| [{line}]({_source_url(source_href, int(line))}) | {rendered} |")
    lines.append("")
    return "\n".join(lines)


def compile_diagram_bundle(
    source: str,
    source_name: str = "input.glyph",
    source_href: str | None = None,
) -> DiagramBundle:
    model = parse_compilation_model(source, source_name)
    ir = build_execution_structure_ir(
        source, source_name, model.program, model.specs, model.machines
    )
    algorithm_ir = build_algorithm_ir(
        source,
        source_name,
        model.program,
        model.blocks,
        model.lambdas,
        model.opaques,
    )
    href = source_href or source_name
    architecture = render_architecture_mermaid(model.architecture, href)
    logic = render_algorithm_mermaid(algorithm_ir, href)
    dataflow = render_dataflow_mermaid(ir, href)
    machine_files = {
        f"machine-{_slug(machine.name)}.mmd": render_machine_mermaid(machine)
        for machine in ir.machines
    }
    temporal = render_temporal_mermaid(ir, href)
    files = {
        "architecture.mmd": architecture,
        "architecture-ir.json": json.dumps(
            model.architecture.to_dict(), ensure_ascii=False, indent=2
        )
        + "\n",
        "logic.mmd": logic,
        "algorithm-ir.json": json.dumps(
            algorithm_ir.to_dict(), ensure_ascii=False, indent=2
        )
        + "\n",
        "execution.mmd": dataflow,
        **machine_files,
        "temporal.mmd": temporal,
        "execution-ir.json": json.dumps(ir.to_dict(), ensure_ascii=False, indent=2)
        + "\n",
        "source-map.json": json.dumps(
            _source_map(ir, model.architecture, algorithm_ir),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    }
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

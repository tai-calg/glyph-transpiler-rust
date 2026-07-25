from __future__ import annotations

from dataclasses import asdict

from .artifacts import CompilationModel
from .compiler import AliasDecl, ExternDecl, FunctionDecl, ProductDecl, SumDecl, TypeRef
from .execution_ir import ExecutionStructureIR
from .state_machine_analysis import analyze_machine
from .state_machine_source_map import remap_machine_analysis_source_lines
from .state_transition_pipeline import enrich_state_transition_ir


IO_STATE_VIEWS_SCHEMA = "glyph.io-state-views"
IO_STATE_VIEWS_VERSION = 2


def empty_io_state_views() -> dict[str, object]:
    return {
        "schema": IO_STATE_VIEWS_SCHEMA,
        "version": IO_STATE_VIEWS_VERSION,
        "source_name": "",
        "summary": {
            "systems": 0,
            "callables": 0,
            "types": 0,
            "machines": 0,
            "state_warnings": 0,
        },
        "io": {"systems": [], "types": []},
        "state": {"machines": []},
        "state_transition_ir": {
            "schema": "glyph.state-transition-ir",
            "version": 2,
        },
    }


def _render_type(ty: TypeRef) -> str:
    if not ty.args:
        return ty.name
    return f"{ty.name}<{','.join(_render_type(arg) for arg in ty.args)}>"


def _source_external_names(model: CompilationModel) -> set[str]:
    """Recover explicit `ext` declarations from the preprocessed public source."""

    names: set[str] = set()
    for original in model.preprocess.source.splitlines():
        code = original.split("#", 1)[0].rstrip()
        stripped = code.strip()
        if not stripped or code[:1].isspace() or not stripped.startswith("ext "):
            continue
        signature = stripped[len("ext ") :].strip()
        open_pos = signature.find("(")
        if open_pos > 0:
            names.add(signature[:open_pos].strip())
    return names


def _signature(
    declaration: FunctionDecl | ExternDecl,
    external_names: set[str],
) -> dict[str, object]:
    if isinstance(declaration, FunctionDecl):
        kind = "function"
    elif declaration.name in external_names:
        kind = "external"
    else:
        kind = "effect"
    return {
        "name": declaration.name,
        "kind": kind,
        "inputs": [
            {"name": parameter.name, "type": _render_type(parameter.ty)}
            for parameter in declaration.params
        ],
        "output": _render_type(declaration.return_type),
        "line": declaration.line,
    }


def _type_declaration(
    declaration: ProductDecl | SumDecl | AliasDecl,
) -> dict[str, object]:
    if isinstance(declaration, ProductDecl):
        return {
            "name": declaration.name,
            "kind": "product",
            "fields": [
                {"name": field.name, "type": _render_type(field.ty)}
                for field in declaration.fields
            ],
            "line": declaration.line,
        }
    if isinstance(declaration, SumDecl):
        return {
            "name": declaration.name,
            "kind": "sum",
            "variants": [
                {
                    "name": variant.name,
                    "tuple": [_render_type(item) for item in variant.tuple_types],
                    "fields": [
                        {"name": field.name, "type": _render_type(field.ty)}
                        for field in variant.fields
                    ],
                }
                for variant in declaration.variants
            ],
            "line": declaration.line,
        }
    return {
        "name": declaration.name,
        "kind": "alias",
        "target": _render_type(declaration.target),
        "line": declaration.line,
    }


def _node_from_component(
    component: object,
    port: object | None,
    signatures: dict[str, dict[str, object]],
) -> dict[str, object]:
    binding = getattr(component, "binding")
    signature = signatures.get(binding or "")
    port_direction = getattr(port, "direction", None)
    port_type = getattr(port, "type", None)

    if signature is None:
        kind = (
            "input"
            if port_direction == "input"
            else "output"
            if port_direction == "output"
            else getattr(component, "kind")
        )
        return {
            "id": getattr(component, "id"),
            "name": getattr(component, "name"),
            "kind": kind,
            "binding": binding,
            "inputs": [],
            "output": port_type,
            "line": getattr(component, "line"),
            "declared_io": port is not None,
            "port_direction": port_direction,
            "port_type": port_type,
        }

    return {
        "id": getattr(component, "id"),
        "name": getattr(component, "name"),
        "kind": signature["kind"],
        "binding": binding,
        "inputs": signature["inputs"],
        "output": signature["output"],
        "line": getattr(component, "line"),
        "declaration_line": signature["line"],
        "declared_io": True,
        "port_direction": port_direction,
        "port_type": port_type,
    }


def _system_edge(edge: object) -> dict[str, object]:
    labels = {
        "data": "data",
        "return": "returns",
        "effect": "effect",
        "responsibility": "flow",
    }
    payload = asdict(edge)
    payload["label"] = labels.get(payload.get("kind"), str(payload.get("kind", "flow")))
    return payload


def _explicit_systems(
    model: CompilationModel,
    signatures: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], set[str]]:
    systems: list[dict[str, object]] = []
    bound: set[str] = set()
    declarations = {item.name: item for item in model.systems}
    for system in model.architecture.systems:
        ports = {item.id: item for item in system.ports}
        nodes: list[dict[str, object]] = []
        for component in system.components:
            if component.binding is not None:
                bound.add(component.binding)
            nodes.append(
                _node_from_component(
                    component,
                    ports.get(component.id),
                    signatures,
                )
            )
        declaration = declarations.get(system.name)
        systems.append(
            {
                "id": system.id,
                "name": system.name,
                "kind": "checked-system-context",
                "entry": declaration.entry_name if declaration is not None else None,
                "line": system.line,
                "ports": [asdict(item) for item in system.ports],
                "nodes": nodes,
                "edges": [_system_edge(edge) for edge in system.edges],
                "evidence": [asdict(item) for item in system.evidence],
            }
        )
    return systems, bound


def _implicit_program(
    execution: ExecutionStructureIR,
    signatures: dict[str, dict[str, object]],
) -> dict[str, object]:
    callable_nodes = {
        node.id: node
        for node in execution.nodes
        if node.kind in {"function", "effect"}
    }
    nodes: list[dict[str, object]] = []
    for node in callable_nodes.values():
        binding = (
            node.label[1:]
            if node.kind == "effect" and node.label.startswith("!")
            else node.label
        )
        signature = signatures.get(binding)
        nodes.append(
            {
                "id": node.id,
                "name": binding,
                "kind": signature["kind"] if signature else node.kind,
                "binding": binding,
                "inputs": signature["inputs"] if signature else [],
                "output": signature["output"] if signature else None,
                "line": node.source.line,
                "declaration_line": signature["line"] if signature else node.source.line,
                "declared_io": signature is not None,
                "port_direction": None,
                "port_type": None,
            }
        )

    seen: set[tuple[str, str]] = set()
    edges: list[dict[str, object]] = []
    for edge in execution.edges:
        pair = (edge.source_id, edge.target_id)
        if (
            edge.kind != "call"
            or edge.source_id not in callable_nodes
            or edge.target_id not in callable_nodes
            or pair in seen
        ):
            continue
        seen.add(pair)
        edges.append(
            {
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "line": edge.source.line,
                "label": "calls",
            }
        )
    return {
        "id": "program_io",
        "name": "Program I/O",
        "kind": "derived-call-graph",
        "entry": None,
        "line": 1,
        "nodes": nodes,
        "edges": edges,
    }


def _unconnected_system(
    signatures: dict[str, dict[str, object]],
    bound: set[str],
) -> dict[str, object] | None:
    remaining = [item for name, item in signatures.items() if name not in bound]
    if not remaining:
        return None
    return {
        "id": "unconnected_declarations",
        "name": "Internal and unconnected declarations",
        "kind": "declaration-set",
        "entry": None,
        "line": min(int(item["line"]) for item in remaining),
        "nodes": [
            {
                "id": f"decl_{item['kind']}_{item['name']}",
                "name": item["name"],
                "kind": item["kind"],
                "binding": item["name"],
                "inputs": item["inputs"],
                "output": item["output"],
                "line": item["line"],
                "declared_io": True,
                "port_direction": None,
                "port_type": None,
            }
            for item in remaining
        ],
        "edges": [],
    }


def build_io_state_views(
    model: CompilationModel,
    execution: ExecutionStructureIR,
) -> dict[str, object]:
    """Project validated System Context and state-machine models for the UI.

    Explicit `system` blocks describe checked boundary flow, not a call graph.
    Sources without a system declaration still receive a derived call-graph view.
    """

    external_names = _source_external_names(model)
    signatures = {
        declaration.name: _signature(declaration, external_names)
        for declaration in model.program.declarations
        if isinstance(declaration, (FunctionDecl, ExternDecl))
    }
    types = [
        _type_declaration(declaration)
        for declaration in model.program.declarations
        if isinstance(declaration, (ProductDecl, SumDecl, AliasDecl))
    ]

    systems, bound = _explicit_systems(model, signatures)
    if systems:
        unconnected = _unconnected_system(signatures, bound)
        if unconnected is not None:
            systems.append(unconnected)
    else:
        systems = [_implicit_program(execution, signatures)]

    raw_machines = [analyze_machine(model, machine) for machine in execution.machines]
    views = {
        "schema": IO_STATE_VIEWS_SCHEMA,
        "version": IO_STATE_VIEWS_VERSION,
        "source_name": execution.source_name,
        "summary": {
            "systems": len(systems),
            "callables": len(signatures),
            "types": len(types),
            "machines": len(raw_machines),
            "state_warnings": 0,
        },
        "io": {"systems": systems, "types": types},
        "state": {"machines": raw_machines},
    }
    result = enrich_state_transition_ir(model, views)
    state = dict(result["state"])
    state["machines"] = [
        remap_machine_analysis_source_lines(model, machine)
        for machine in state["machines"]
    ]
    result["state"] = state
    return result

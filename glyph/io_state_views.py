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


def _signature(declaration: FunctionDecl | ExternDecl) -> dict[str, object]:
    return {
        "name": declaration.name,
        "kind": "effect" if isinstance(declaration, ExternDecl) else "function",
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


def _node_from_signature(
    node_id: str,
    display_name: str,
    component_kind: str,
    binding: str | None,
    line: int,
    signatures: dict[str, dict[str, object]],
) -> dict[str, object]:
    signature = signatures.get(binding or "")
    if signature is None:
        return {
            "id": node_id,
            "name": display_name,
            "kind": component_kind,
            "binding": binding,
            "inputs": [],
            "output": None,
            "line": line,
            "declared_io": False,
        }
    return {
        "id": node_id,
        "name": display_name,
        "kind": signature["kind"],
        "binding": binding,
        "inputs": signature["inputs"],
        "output": signature["output"],
        "line": line,
        "declaration_line": signature["line"],
        "declared_io": True,
    }


def _explicit_systems(
    model: CompilationModel,
    signatures: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], set[str]]:
    systems: list[dict[str, object]] = []
    bound: set[str] = set()
    for system in model.architecture.systems:
        nodes: list[dict[str, object]] = []
        for component in system.components:
            if component.binding is not None:
                bound.add(component.binding)
            nodes.append(
                _node_from_signature(
                    component.id,
                    component.name,
                    component.kind,
                    component.binding,
                    component.line,
                    signatures,
                )
            )
        systems.append(
            {
                "id": system.id,
                "name": system.name,
                "kind": "declared-system",
                "line": system.line,
                "nodes": nodes,
                "edges": [asdict(edge) for edge in system.edges],
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
        nodes.append(
            _node_from_signature(
                node.id,
                binding,
                node.kind,
                binding,
                node.source.line,
                signatures,
            )
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
            }
        )
    return {
        "id": "program_io",
        "name": "Program I/O",
        "kind": "derived-call-graph",
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
        "name": "Unconnected declarations",
        "kind": "declaration-set",
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
            }
            for item in remaining
        ],
        "edges": [],
    }


def build_io_state_views(
    model: CompilationModel,
    execution: ExecutionStructureIR,
) -> dict[str, object]:
    """Project validated compiler models into I/O and StateTransitionIR v2.

    Transition semantics are finalized before source-map restoration and before any
    renderer sees the result. Renderers therefore consume only canonical fields.
    """

    signatures = {
        declaration.name: _signature(declaration)
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

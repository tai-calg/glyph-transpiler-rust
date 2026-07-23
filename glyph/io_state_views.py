from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from .artifacts import CompilationModel
from .compiler import (
    AliasDecl,
    BinaryExpr,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    NameExpr,
    ProductDecl,
    SumDecl,
    TryExpr,
    TypeRef,
    UnaryExpr,
)
from .execution_ir import (
    ExecutionStructureIR,
    MachineTransitionView,
    SourceRef,
    render_expr,
)


IO_STATE_VIEWS_SCHEMA = "glyph.io-state-views"
IO_STATE_VIEWS_VERSION = 1


def empty_io_state_views() -> dict[str, object]:
    return {
        "schema": IO_STATE_VIEWS_SCHEMA,
        "version": IO_STATE_VIEWS_VERSION,
        "source_name": "",
        "summary": {"systems": 0, "callables": 0, "types": 0, "machines": 0},
        "io": {"systems": [], "types": []},
        "state": {"machines": []},
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


def _walk_expr(expr: Expr) -> Iterable[Expr]:
    yield expr
    if isinstance(expr, UnaryExpr):
        yield from _walk_expr(expr.expr)
    elif isinstance(expr, TryExpr):
        yield from _walk_expr(expr.expr)
    elif isinstance(expr, BinaryExpr):
        yield from _walk_expr(expr.left)
        yield from _walk_expr(expr.right)
    elif isinstance(expr, FieldExpr):
        yield from _walk_expr(expr.base)
    elif isinstance(expr, CallExpr):
        yield from _walk_expr(expr.callee)
        for argument in expr.args:
            yield from _walk_expr(argument)


def _unwrap_state_expr(expr: Expr) -> Expr:
    if isinstance(expr, TryExpr):
        return _unwrap_state_expr(expr.expr)
    if (
        isinstance(expr, CallExpr)
        and isinstance(expr.callee, NameExpr)
        and expr.callee.name == "Ok"
        and len(expr.args) == 1
    ):
        return _unwrap_state_expr(expr.args[0])
    return expr


def _selector_comparison(
    expr: Expr,
    state_param: str,
    selector_field: str,
    variants: set[str],
) -> set[str]:
    found: set[str] = set()
    for item in _walk_expr(expr):
        if not isinstance(item, BinaryExpr) or item.op != "==":
            continue
        for left, right in ((item.left, item.right), (item.right, item.left)):
            if (
                isinstance(left, FieldExpr)
                and isinstance(left.base, NameExpr)
                and left.base.name == state_param
                and left.field == selector_field
                and isinstance(right, NameExpr)
                and right.name in variants
            ):
                found.add(right.name)
    return found


def _state_target(
    expr: Expr,
    state_decl: ProductDecl,
    selector_index: int,
    variants: set[str],
    state_param: str,
) -> str | None:
    value = _unwrap_state_expr(expr)
    if isinstance(value, NameExpr) and value.name == state_param:
        return "__same__"
    if not (
        isinstance(value, CallExpr)
        and isinstance(value.callee, NameExpr)
        and value.callee.name == state_decl.name
        and len(value.args) == len(state_decl.fields)
    ):
        return None
    selected = value.args[selector_index]
    if isinstance(selected, NameExpr) and selected.name in variants:
        return selected.name
    return None


def _called_functions(
    expr: Expr,
    functions: dict[str, FunctionDecl],
) -> tuple[str, ...]:
    names: list[str] = []
    for item in _walk_expr(expr):
        if (
            isinstance(item, CallExpr)
            and isinstance(item.callee, NameExpr)
            and item.callee.name in functions
            and item.callee.name not in names
        ):
            names.append(item.callee.name)
    return tuple(names)


def _transition_function(
    name: str,
    functions: dict[str, FunctionDecl],
    state_decl: ProductDecl,
    selector_index: int,
    selector_field: str,
    variants: set[str],
    visited: set[str],
) -> list[MachineTransitionView]:
    if name in visited or name not in functions:
        return []
    visited = {*visited, name}
    declaration = functions[name]
    state_param = declaration.params[0].name if declaration.params else "state"
    transitions: list[MachineTransitionView] = []

    if declaration.guards:
        for clause in declaration.guards:
            target = _state_target(
                clause.value,
                state_decl,
                selector_index,
                variants,
                state_param,
            )
            if target is None:
                for nested_name in _called_functions(clause.value, functions):
                    transitions.extend(
                        _transition_function(
                            nested_name,
                            functions,
                            state_decl,
                            selector_index,
                            selector_field,
                            variants,
                            visited,
                        )
                    )
                continue
            sources = (
                _selector_comparison(
                    clause.condition,
                    state_param,
                    selector_field,
                    variants,
                )
                if clause.condition is not None
                else set()
            )
            if not sources:
                sources = {"*"}
            condition = (
                render_expr(clause.condition)
                if clause.condition is not None
                else "otherwise"
            )
            for source in sorted(sources):
                resolved_target = source if target == "__same__" and source != "*" else target
                if resolved_target == "__same__":
                    resolved_target = "*"
                transitions.append(
                    MachineTransitionView(
                        source,
                        resolved_target,
                        condition,
                        SourceRef(clause.line),
                    )
                )
        return transitions

    if declaration.expression is None:
        return transitions
    target = _state_target(
        declaration.expression,
        state_decl,
        selector_index,
        variants,
        state_param,
    )
    if target is not None:
        return [
            MachineTransitionView(
                "*",
                "*" if target == "__same__" else target,
                "next",
                SourceRef(declaration.line),
            )
        ]
    for nested_name in _called_functions(declaration.expression, functions):
        transitions.extend(
            _transition_function(
                nested_name,
                functions,
                state_decl,
                selector_index,
                selector_field,
                variants,
                visited,
            )
        )
    return transitions


def _machine_transitions(
    model: CompilationModel,
    machine_name: str,
) -> list[dict[str, object]]:
    machine = next((item for item in model.machines if item.name == machine_name), None)
    if machine is None or not isinstance(machine.selector, FieldExpr):
        return []
    products = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, ProductDecl)
    }
    sums = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, SumDecl)
    }
    functions = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, FunctionDecl)
    }
    state_decl = products.get(machine.state_param.ty.name)
    if state_decl is None:
        return []
    selector_index = next(
        (
            index
            for index, field in enumerate(state_decl.fields)
            if field.name == machine.selector.field
        ),
        None,
    )
    if selector_index is None:
        return []
    selector_sum = sums.get(state_decl.fields[selector_index].ty.name)
    if selector_sum is None:
        return []
    variants = {variant.name for variant in selector_sum.variants}
    next_expr = machine.next_expr
    if not isinstance(next_expr, CallExpr) or not isinstance(next_expr.callee, NameExpr):
        return []
    transitions = _transition_function(
        next_expr.callee.name,
        functions,
        state_decl,
        selector_index,
        machine.selector.field,
        variants,
        set(),
    )
    unique: list[MachineTransitionView] = []
    seen: set[tuple[str, str, str, int]] = set()
    for transition in transitions:
        key = (
            transition.source_state,
            transition.target_state,
            transition.condition,
            transition.source.line,
        )
        if key not in seen:
            seen.add(key)
            unique.append(transition)
    return [asdict(transition) for transition in unique]


def build_io_state_views(
    model: CompilationModel,
    execution: ExecutionStructureIR,
) -> dict[str, object]:
    """Project validated compiler IR into generic I/O and state-machine views.

    This projection does not parse Glyph source and does not infer business meaning.
    Declared systems provide the I/O topology. When no system exists, the compiler
    call graph is used. State transitions come only from validated machine and
    function ASTs, including compiler-generated helpers for immutable `:=` blocks.
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

    machines: list[dict[str, object]] = []
    for machine in execution.machines:
        projected = asdict(machine)
        traced = _machine_transitions(model, machine.name)
        if traced:
            projected["transitions"] = traced
        machines.append(projected)

    return {
        "schema": IO_STATE_VIEWS_SCHEMA,
        "version": IO_STATE_VIEWS_VERSION,
        "source_name": execution.source_name,
        "summary": {
            "systems": len(systems),
            "callables": len(signatures),
            "types": len(types),
            "machines": len(machines),
        },
        "io": {"systems": systems, "types": types},
        "state": {"machines": machines},
    }

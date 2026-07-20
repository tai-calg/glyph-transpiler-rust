from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

from .compiler import (
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    NameExpr,
    NumberExpr,
    ProductDecl,
    Program,
    SumDecl,
    TryExpr,
    UnaryExpr,
)
from .machine import MachineDecl
from .temporal import SpecDecl


@dataclass(frozen=True)
class SourceRef:
    line: int
    column: int = 1


@dataclass(frozen=True)
class ExecutionNode:
    id: str
    kind: str
    label: str
    source: SourceRef


@dataclass(frozen=True)
class ExecutionEdge:
    source_id: str
    target_id: str
    kind: str
    label: str
    source: SourceRef


@dataclass(frozen=True)
class MachineStateView:
    name: str
    terminal: str | None
    source: SourceRef


@dataclass(frozen=True)
class MachineTransitionView:
    source_state: str
    target_state: str
    condition: str
    source: SourceRef


@dataclass(frozen=True)
class MachineView:
    name: str
    state_type: str
    selector: str
    initial_state: str
    next_function: str
    success_state: str
    failure_state: str
    states: tuple[MachineStateView, ...]
    transitions: tuple[MachineTransitionView, ...]
    source: SourceRef


@dataclass(frozen=True)
class TemporalView:
    name: str
    formula: str
    reference_monitor: str
    streaming_monitor: str
    source: SourceRef


@dataclass(frozen=True)
class ExecutionStructureIR:
    source_name: str
    nodes: tuple[ExecutionNode, ...]
    edges: tuple[ExecutionEdge, ...]
    machines: tuple[MachineView, ...]
    temporal: tuple[TemporalView, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _pascal_case(name: str) -> str:
    result = "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)
    return result or "Temporal"


def _node_id(prefix: str, name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)
    return f"{prefix}_{safe}"


def render_expr(expr: Expr, parent_precedence: int = 0) -> str:
    precedence = {
        "|": 10,
        "&": 20,
        "==": 30,
        "!=": 30,
        "<": 30,
        ">": 30,
        "<=": 30,
        ">=": 30,
        "+": 40,
        "-": 40,
        "*": 50,
        "/": 50,
    }
    if isinstance(expr, NameExpr):
        return expr.name
    if isinstance(expr, NumberExpr):
        return expr.value
    if isinstance(expr, BoolExpr):
        return "true" if expr.value else "false"
    if isinstance(expr, FieldExpr):
        return f"{render_expr(expr.base, 70)}.{expr.field}"
    if isinstance(expr, TryExpr):
        return f"{render_expr(expr.expr, 70)}?"
    if isinstance(expr, UnaryExpr):
        return f"{expr.op}{render_expr(expr.expr, 60)}"
    if isinstance(expr, CallExpr):
        return (
            f"{render_expr(expr.callee, 70)}("
            + ",".join(render_expr(arg) for arg in expr.args)
            + ")"
        )
    if isinstance(expr, BinaryExpr):
        current = precedence.get(expr.op, 0)
        text = (
            f"{render_expr(expr.left, current)}"
            f"{expr.op}"
            f"{render_expr(expr.right, current + 1)}"
        )
        return f"({text})" if current < parent_precedence else text
    return type(expr).__name__


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
        for arg in expr.args:
            yield from _walk_expr(arg)


def _pipeline(expr: Expr, callable_names: set[str]) -> list[tuple[str, bool]]:
    if isinstance(expr, TryExpr):
        stages = _pipeline(expr.expr, callable_names)
        if stages:
            name, _ = stages[-1]
            stages[-1] = (name, True)
        return stages
    if isinstance(expr, CallExpr):
        stages: list[tuple[str, bool]] = []
        for arg in expr.args:
            stages.extend(_pipeline(arg, callable_names))
        if isinstance(expr.callee, NameExpr) and expr.callee.name in callable_names:
            stages.append((expr.callee.name, False))
        return stages
    if isinstance(expr, BinaryExpr):
        return _pipeline(expr.left, callable_names) + _pipeline(expr.right, callable_names)
    if isinstance(expr, UnaryExpr):
        return _pipeline(expr.expr, callable_names)
    if isinstance(expr, FieldExpr):
        return _pipeline(expr.base, callable_names)
    return []


class _DataflowBuilder:
    def __init__(self, program: Program):
        self.program = program
        self.nodes: dict[str, ExecutionNode] = {}
        self.edges: list[ExecutionEdge] = []
        self.callables = {
            decl.name
            for decl in program.declarations
            if isinstance(decl, (FunctionDecl, ExternDecl))
        }
        self.functions = {
            decl.name: decl
            for decl in program.declarations
            if isinstance(decl, FunctionDecl)
        }

    def build(self) -> tuple[tuple[ExecutionNode, ...], tuple[ExecutionEdge, ...]]:
        for decl in self.program.declarations:
            if isinstance(decl, FunctionDecl):
                self._add_node(
                    _node_id("fn", decl.name), "function", decl.name, SourceRef(decl.line)
                )
            elif isinstance(decl, ExternDecl):
                self._add_node(
                    _node_id("effect", decl.name),
                    "effect",
                    f"!{decl.name}",
                    SourceRef(decl.line),
                )

        for decl in self.functions.values():
            self._function(decl)
        return tuple(self.nodes.values()), tuple(self.edges)

    def _callable_node(self, name: str) -> str:
        return _node_id("fn", name) if name in self.functions else _node_id("effect", name)

    def _add_node(self, node_id: str, kind: str, label: str, source: SourceRef) -> None:
        self.nodes.setdefault(node_id, ExecutionNode(node_id, kind, label, source))

    def _add_edge(
        self,
        source_id: str,
        target_id: str,
        kind: str,
        label: str,
        source: SourceRef,
    ) -> None:
        self.edges.append(ExecutionEdge(source_id, target_id, kind, label, source))

    def _function(self, decl: FunctionDecl) -> None:
        entry = _node_id("fn", decl.name)
        if decl.expression is not None:
            self._attach_expression(entry, decl.expression, decl.line, "")
            return

        previous_false: str | None = None
        for index, clause in enumerate(decl.guards):
            if clause.condition is None:
                start = previous_false or entry
                self._attach_expression(start, clause.value, clause.line, "otherwise")
                continue

            decision = _node_id("guard", f"{decl.name}_{index + 1}")
            self._add_node(
                decision,
                "decision",
                render_expr(clause.condition),
                SourceRef(clause.line),
            )
            if previous_false is None:
                self._add_edge(entry, decision, "control", "", SourceRef(clause.line))
            else:
                self._add_edge(
                    previous_false, decision, "control", "false", SourceRef(clause.line)
                )
            branch = _node_id("branch", f"{decl.name}_{index + 1}")
            self._add_node(branch, "branch", "true", SourceRef(clause.line))
            self._add_edge(decision, branch, "control", "true", SourceRef(clause.line))
            self._attach_expression(branch, clause.value, clause.line, "")
            previous_false = decision

    def _attach_expression(
        self, start: str, expr: Expr, line: int, first_label: str
    ) -> None:
        stages = _pipeline(expr, self.callables)
        current = start
        pending_label = first_label
        error_node = _node_id("error", f"{start}_{line}")

        for name, propagates in stages:
            target = self._callable_node(name)
            self._add_edge(current, target, "call", pending_label or "call", SourceRef(line))
            current = target
            pending_label = "Ok" if propagates else ""
            if propagates:
                self._add_node(error_node, "error", "Err", SourceRef(line))
                self._add_edge(current, error_node, "error", "Err", SourceRef(line))

        result = _node_id("result", f"{start}_{line}_{len(self.nodes)}")
        label = render_expr(expr)
        kind = "error" if label.startswith("Err(") else "result"
        self._add_node(result, kind, label, SourceRef(line))
        self._add_edge(current, result, "return", pending_label or "return", SourceRef(line))


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
    expr: Expr, state_param: str, selector_field: str, variants: set[str]
) -> set[str]:
    found: set[str] = set()
    for item in _walk_expr(expr):
        if not isinstance(item, BinaryExpr) or item.op != "==":
            continue
        pairs = ((item.left, item.right), (item.right, item.left))
        for left, right in pairs:
            if not (
                isinstance(left, FieldExpr)
                and isinstance(left.base, NameExpr)
                and left.base.name == state_param
                and left.field == selector_field
                and isinstance(right, NameExpr)
                and right.name in variants
            ):
                continue
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
    decl = functions[name]
    state_param = decl.params[0].name if decl.params else "state"
    transitions: list[MachineTransitionView] = []

    if decl.guards:
        for clause in decl.guards:
            target = _state_target(
                clause.value, state_decl, selector_index, variants, state_param
            )
            if target is None:
                nested = _unwrap_state_expr(clause.value)
                if isinstance(nested, CallExpr) and isinstance(nested.callee, NameExpr):
                    transitions.extend(
                        _transition_function(
                            nested.callee.name,
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
                    clause.condition, state_param, selector_field, variants
                )
                if clause.condition is not None
                else set()
            )
            if not sources:
                sources = {"*"}
            condition = (
                render_expr(clause.condition) if clause.condition is not None else "otherwise"
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

    if decl.expression is None:
        return transitions
    target = _state_target(
        decl.expression, state_decl, selector_index, variants, state_param
    )
    if target is not None:
        transitions.append(
            MachineTransitionView(
                "*", "*" if target == "__same__" else target, "next", SourceRef(decl.line)
            )
        )
        return transitions
    nested = _unwrap_state_expr(decl.expression)
    if isinstance(nested, CallExpr) and isinstance(nested.callee, NameExpr):
        return _transition_function(
            nested.callee.name,
            functions,
            state_decl,
            selector_index,
            selector_field,
            variants,
            visited,
        )
    return transitions


def _machine_view(program: Program, machine: MachineDecl) -> MachineView:
    products = {
        decl.name: decl for decl in program.declarations if isinstance(decl, ProductDecl)
    }
    sums = {decl.name: decl for decl in program.declarations if isinstance(decl, SumDecl)}
    functions = {
        decl.name: decl for decl in program.declarations if isinstance(decl, FunctionDecl)
    }
    state_decl = products[machine.state_param.ty.name]
    selector = machine.selector
    assert isinstance(selector, FieldExpr)
    selector_index = next(
        index for index, field in enumerate(state_decl.fields) if field.name == selector.field
    )
    selector_sum = sums[state_decl.fields[selector_index].ty.name]
    variants = {variant.name for variant in selector_sum.variants}
    initial = _unwrap_state_expr(machine.initial)
    assert isinstance(initial, CallExpr)
    initial_variant = initial.args[selector_index]
    assert isinstance(initial_variant, NameExpr)
    next_call = machine.next_expr
    assert isinstance(next_call, CallExpr) and isinstance(next_call.callee, NameExpr)

    states = tuple(
        MachineStateView(
            variant.name,
            "success"
            if variant.name == machine.success
            else "failure"
            if variant.name == machine.failure
            else None,
            SourceRef(
                machine.success_line
                if variant.name == machine.success
                else machine.failure_line
                if variant.name == machine.failure
                else machine.line
            ),
        )
        for variant in selector_sum.variants
    )
    transitions = tuple(
        _transition_function(
            next_call.callee.name,
            functions,
            state_decl,
            selector_index,
            selector.field,
            variants,
            set(),
        )
    )
    return MachineView(
        name=machine.name,
        state_type=state_decl.name,
        selector=render_expr(machine.selector),
        initial_state=initial_variant.name,
        next_function=next_call.callee.name,
        success_state=machine.success,
        failure_state=machine.failure,
        states=states,
        transitions=transitions,
        source=SourceRef(machine.line),
    )


def _formula_from_source(source_lines: Sequence[str], spec: SpecDecl) -> str:
    if not 1 <= spec.line <= len(source_lines):
        return spec.name
    clean = source_lines[spec.line - 1].split("#", 1)[0].strip()
    separator = clean.find("=")
    return clean[separator + 1 :].strip() if separator >= 0 else clean


def build_execution_structure_ir(
    source: str,
    source_name: str,
    program: Program,
    specs: Sequence[SpecDecl],
    machines: Sequence[MachineDecl],
) -> ExecutionStructureIR:
    nodes, edges = _DataflowBuilder(program).build()
    source_lines = source.splitlines()
    temporal = tuple(
        TemporalView(
            name=spec.name,
            formula=_formula_from_source(source_lines, spec),
            reference_monitor=f"{_pascal_case(spec.name)}Monitor",
            streaming_monitor=f"{_pascal_case(spec.name)}StreamingMonitor",
            source=SourceRef(spec.line),
        )
        for spec in specs
    )
    return ExecutionStructureIR(
        source_name=source_name,
        nodes=nodes,
        edges=edges,
        machines=tuple(_machine_view(program, machine) for machine in machines),
        temporal=temporal,
    )

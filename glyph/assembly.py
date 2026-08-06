from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping, Sequence

from .compiler import (
    AliasDecl,
    BinaryExpr,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    GlyphError,
    NameExpr,
    Program,
    TryExpr,
    TypeRef,
    UnaryExpr,
)
from .machine import MachineDecl


_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_ASSEMBLY_HEADER_RE = re.compile(rf"assembly\s+({_NAME})\s*$")
_INSTANCE_RE = re.compile(rf"({_NAME})\s*=\s*({_NAME})\s*$")
_ROUTE_RE = re.compile(
    rf"({_NAME})\.({_NAME})\s*->\s*({_NAME})\.({_NAME})\s*$"
)


@dataclass(frozen=True)
class AssemblyInstance:
    name: str
    machine: str
    line: int


@dataclass(frozen=True)
class AssemblyRoute:
    source_instance: str
    effect: str
    target_instance: str
    input: str
    line: int


@dataclass(frozen=True)
class AssemblyDecl:
    name: str
    instances: tuple[AssemblyInstance, ...]
    routes: tuple[AssemblyRoute, ...]
    line: int


@dataclass(frozen=True)
class AssemblyDiagnostic:
    severity: str
    code: str
    message: str
    line: int


@dataclass(frozen=True)
class MachineAssemblyIR:
    schema: str
    version: int
    name: str
    delivery: str
    reentrant_reaction: str
    instances: tuple[dict[str, object], ...]
    routes: tuple[dict[str, object], ...]
    diagnostics: tuple[AssemblyDiagnostic, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "version": self.version,
            "name": self.name,
            "delivery": self.delivery,
            "reentrant_reaction": self.reentrant_reaction,
            "instances": [dict(item) for item in self.instances],
            "routes": [dict(item) for item in self.routes],
            "diagnostics": [
                {
                    "severity": item.severity,
                    "code": item.code,
                    "message": item.message,
                    "line": item.line,
                }
                for item in self.diagnostics
            ],
        }


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].rstrip()


def extract_assemblies(source: str) -> tuple[str, tuple[AssemblyDecl, ...]]:
    """Extract top-level assembly blocks while preserving source line numbers."""

    raw_lines = source.splitlines()
    output = list(raw_lines)
    assemblies: list[AssemblyDecl] = []
    seen: dict[str, int] = {}
    i = 0

    while i < len(raw_lines):
        original = raw_lines[i]
        clean = _strip_comment(original)
        if not clean.strip() or clean[0].isspace() or not clean.startswith("assembly "):
            i += 1
            continue

        line_no = i + 1
        header = _ASSEMBLY_HEADER_RE.fullmatch(clean)
        if header is None:
            raise GlyphError(f"{line_no}行目: assembly Name の形式が必要")
        name = header.group(1)
        if name in seen:
            raise GlyphError(
                f"{line_no}行目: assembly '{name}' は{seen[name]}行目で既に定義済み"
            )

        output[i] = ""
        i += 1
        instances: list[AssemblyInstance] = []
        routes: list[AssemblyRoute] = []

        while i < len(raw_lines):
            body_original = raw_lines[i]
            body_clean = _strip_comment(body_original)
            if body_clean.strip() and not body_original[0].isspace():
                break
            output[i] = ""
            if not body_clean.strip():
                i += 1
                continue

            body_line = i + 1
            stripped = body_clean.strip()
            route_match = _ROUTE_RE.fullmatch(stripped)
            if route_match is not None:
                routes.append(
                    AssemblyRoute(
                        source_instance=route_match.group(1),
                        effect=route_match.group(2),
                        target_instance=route_match.group(3),
                        input=route_match.group(4),
                        line=body_line,
                    )
                )
                i += 1
                continue

            instance_match = _INSTANCE_RE.fullmatch(stripped)
            if instance_match is not None:
                instances.append(
                    AssemblyInstance(
                        name=instance_match.group(1),
                        machine=instance_match.group(2),
                        line=body_line,
                    )
                )
                i += 1
                continue

            raise GlyphError(
                f"{body_line}行目: assembly内は instance=Machine または "
                "instance.effect -> instance.input の形式で記述する"
            )

        if not instances:
            raise GlyphError(f"{line_no}行目: assembly '{name}' にMachine instanceがない")

        assemblies.append(
            AssemblyDecl(
                name=name,
                instances=tuple(instances),
                routes=tuple(routes),
                line=line_no,
            )
        )
        seen[name] = line_no

    suffix = "\n" if source.endswith("\n") else ""
    return "\n".join(output) + suffix, tuple(assemblies)


def _render_type(ty: TypeRef) -> str:
    if not ty.args:
        return ty.name
    return f"{ty.name}<{','.join(_render_type(item) for item in ty.args)}>"


def _resolve_alias(ty: TypeRef, aliases: Mapping[str, TypeRef]) -> TypeRef:
    current = ty
    seen: set[str] = set()
    while not current.args and current.name in aliases and current.name not in seen:
        seen.add(current.name)
        current = aliases[current.name]
    return current


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


def _direct_calls(expr: Expr) -> tuple[str, ...]:
    calls: list[str] = []
    for item in _walk_expr(expr):
        if isinstance(item, CallExpr) and isinstance(item.callee, NameExpr):
            if item.callee.name not in calls:
                calls.append(item.callee.name)
    return tuple(calls)


def _reachable_effects(
    machine: MachineDecl,
    functions: Mapping[str, FunctionDecl],
    effects: Mapping[str, ExternDecl],
) -> set[str]:
    pending = list(_direct_calls(machine.next_expr))
    visited: set[str] = set()
    reachable: set[str] = set()

    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        if name in effects:
            reachable.add(name)
            continue
        function = functions.get(name)
        if function is None:
            continue
        expressions: list[Expr] = []
        if function.expression is not None:
            expressions.append(function.expression)
        for clause in function.guards:
            if clause.condition is not None:
                expressions.append(clause.condition)
            expressions.append(clause.value)
        for expression in expressions:
            pending.extend(_direct_calls(expression))

    return reachable


def _cycle_diagnostics(assembly: AssemblyDecl) -> tuple[AssemblyDiagnostic, ...]:
    adjacency: dict[str, set[str]] = {
        instance.name: set() for instance in assembly.instances
    }
    route_lines: dict[tuple[str, str], int] = {}
    for route in assembly.routes:
        adjacency.setdefault(route.source_instance, set()).add(route.target_instance)
        route_lines[(route.source_instance, route.target_instance)] = route.line

    visiting: set[str] = set()
    visited: set[str] = set()
    diagnostics: list[AssemblyDiagnostic] = []

    def visit(node: str, path: tuple[str, ...]) -> None:
        if node in visiting:
            start = path.index(node) if node in path else 0
            cycle = (*path[start:], node)
            edge = (cycle[-2], cycle[-1])
            diagnostics.append(
                AssemblyDiagnostic(
                    severity="warning",
                    code="immediate-route-cycle",
                    message=(
                        "即時route循環がある: " + " -> ".join(cycle)
                        + "。実行時の再入は禁止される"
                    ),
                    line=route_lines.get(edge, assembly.line),
                )
            )
            return
        if node in visited:
            return
        visiting.add(node)
        for target in adjacency.get(node, ()):
            visit(target, (*path, node))
        visiting.remove(node)
        visited.add(node)

    for instance in adjacency:
        visit(instance, ())

    unique: list[AssemblyDiagnostic] = []
    seen_messages: set[str] = set()
    for item in diagnostics:
        if item.message in seen_messages:
            continue
        seen_messages.add(item.message)
        unique.append(item)
    return tuple(unique)


def validate_assemblies(
    program: Program,
    machines: Sequence[MachineDecl],
    assemblies: Sequence[AssemblyDecl],
) -> tuple[MachineAssemblyIR, ...]:
    machine_by_name = {machine.name: machine for machine in machines}
    functions = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, FunctionDecl)
    }
    effects = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, ExternDecl)
    }
    aliases = {
        declaration.name: declaration.target
        for declaration in program.declarations
        if isinstance(declaration, AliasDecl)
    }

    result: list[MachineAssemblyIR] = []
    for assembly in assemblies:
        instance_by_name: dict[str, AssemblyInstance] = {}
        instance_machine: dict[str, MachineDecl] = {}
        for instance in assembly.instances:
            previous = instance_by_name.get(instance.name)
            if previous is not None:
                raise GlyphError(
                    f"{instance.line}行目: instance '{instance.name}' は"
                    f"{previous.line}行目で既に定義済み"
                )
            machine = machine_by_name.get(instance.machine)
            if machine is None:
                raise GlyphError(
                    f"{instance.line}行目: machine '{instance.machine}' が定義されていない"
                )
            instance_by_name[instance.name] = instance
            instance_machine[instance.name] = machine

        reachable_by_instance = {
            instance_name: _reachable_effects(machine, functions, effects)
            for instance_name, machine in instance_machine.items()
        }
        routed_sources: dict[tuple[str, str], int] = {}
        route_ir: list[dict[str, object]] = []

        for order, route in enumerate(assembly.routes, start=1):
            source = instance_by_name.get(route.source_instance)
            if source is None:
                raise GlyphError(
                    f"{route.line}行目: source instance '{route.source_instance}' が存在しない"
                )
            target = instance_by_name.get(route.target_instance)
            if target is None:
                raise GlyphError(
                    f"{route.line}行目: target instance '{route.target_instance}' が存在しない"
                )
            if route.source_instance == route.target_instance:
                raise GlyphError(
                    f"{route.line}行目: v1では同一Machine instanceへの即時routeを許可しない"
                )

            effect = effects.get(route.effect)
            if effect is None:
                raise GlyphError(
                    f"{route.line}行目: !effect '{route.effect}' が定義されていない"
                )
            if route.effect not in reachable_by_instance[route.source_instance]:
                raise GlyphError(
                    f"{route.line}行目: effect '{route.effect}' はMachine "
                    f"'{source.machine}' の遷移から到達できない"
                )

            source_key = (route.source_instance, route.effect)
            previous_line = routed_sources.get(source_key)
            if previous_line is not None:
                raise GlyphError(
                    f"{route.line}行目: '{route.source_instance}.{route.effect}' は"
                    f"{previous_line}行目で既にroute済み。v1は単一接続のみ"
                )
            routed_sources[source_key] = route.line

            target_machine = instance_machine[route.target_instance]
            target_param = next(
                (param for param in target_machine.input_params if param.name == route.input),
                None,
            )
            if target_param is None:
                available = ", ".join(param.name for param in target_machine.input_params)
                raise GlyphError(
                    f"{route.line}行目: Machine '{target.machine}' に入力 '{route.input}' がない"
                    + (f"。使用可能: {available}" if available else "")
                )

            source_type = _resolve_alias(effect.return_type, aliases)
            target_type = _resolve_alias(target_param.ty, aliases)
            if source_type != target_type:
                raise GlyphError(
                    f"{route.line}行目: route型不一致: "
                    f"{route.source_instance}.{route.effect} は {_render_type(effect.return_type)}、"
                    f"{route.target_instance}.{route.input} は {_render_type(target_param.ty)}"
                )

            route_ir.append(
                {
                    "source_instance": route.source_instance,
                    "source_machine": source.machine,
                    "effect": route.effect,
                    "value_type": _render_type(effect.return_type),
                    "target_instance": route.target_instance,
                    "target_machine": target.machine,
                    "input": route.input,
                    "delivery": "immediate",
                    "order": order,
                    "line": route.line,
                }
            )

        result.append(
            MachineAssemblyIR(
                schema="glyph.machine-assembly-ir",
                version=1,
                name=assembly.name,
                delivery="immediate",
                reentrant_reaction="forbidden",
                instances=tuple(
                    {
                        "name": item.name,
                        "machine": item.machine,
                        "line": item.line,
                    }
                    for item in assembly.instances
                ),
                routes=tuple(route_ir),
                diagnostics=_cycle_diagnostics(assembly),
            )
        )

    return tuple(result)

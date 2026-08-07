from __future__ import annotations

from collections.abc import Iterator, Mapping as MappingABC
from dataclasses import dataclass
import re
from typing import Iterable, Mapping, Sequence

from .compiler import (
    AliasDecl,
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    GlyphError,
    NameExpr,
    ProductDecl,
    Program,
    SumDecl,
    TryExpr,
    TypeRef,
    UnaryExpr,
)
from .machine import MachineDecl


_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_ASSEMBLY_HEADER_RE = re.compile(rf"assembly\s+({_NAME})\s*$")
_ASSEMBLY_PREFIX_RE = re.compile(r"assembly(?:\s|$)")
_INSTANCE_RE = re.compile(rf"({_NAME})\s*=\s*({_NAME})\s*$")
_ROUTE_RE = re.compile(
    rf"({_NAME})\.({_NAME})\s*->\s*({_NAME})\.({_NAME})\s*$"
)
_BUILTIN_TYPE_NAMES = {
    "R": "Result",
    "O": "Option",
    "V": "Vec",
    "S": "String",
}


class FrozenMapping(tuple, MappingABC[str, object]):
    """Tuple-backed recursively immutable mapping for Assembly IR records."""

    __slots__ = ()

    def __new__(cls, values: Mapping[str, object]):
        if not isinstance(values, Mapping):
            raise TypeError("FrozenMappingにはMappingが必要")
        return tuple.__new__(
            cls,
            tuple((str(key), _freeze(value)) for key, value in values.items()),
        )

    def __getitem__(self, key: str) -> object:
        for item_key, item_value in tuple.__iter__(self):
            if item_key == key:
                return item_value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in tuple.__iter__(self))

    def __repr__(self) -> str:
        body = ", ".join(
            f"{key!r}: {value!r}"
            for key, value in tuple.__iter__(self)
        )
        return f"FrozenMapping({{{body}}})"

    def __deepcopy__(self, memo):
        return self


_IMMUTABLE_IR_SCALARS = (str, bytes, int, float, bool, type(None))


def _freeze(value: object) -> object:
    if isinstance(value, FrozenMapping):
        return value
    if isinstance(value, Mapping):
        return FrozenMapping(value)
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    if isinstance(value, _IMMUTABLE_IR_SCALARS):
        return value
    raise TypeError(
        "Assembly IRに保持できない可変または不透明な値: "
        f"{type(value).__module__}.{type(value).__qualname__}"
    )


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, frozenset):
        return [_thaw(item) for item in sorted(value, key=repr)]
    return value


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

    def to_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "line": self.line,
        }


@dataclass(frozen=True)
class MachineAssemblyIR:
    schema: str
    version: int
    name: str
    delivery: str
    state_commit: str
    reentrant_reaction: str
    instances: tuple[Mapping[str, object], ...]
    routes: tuple[Mapping[str, object], ...]
    diagnostics: tuple[AssemblyDiagnostic, ...] = ()
    types: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "instances", tuple(_freeze(item) for item in self.instances))
        object.__setattr__(self, "routes", tuple(_freeze(item) for item in self.routes))
        object.__setattr__(self, "types", tuple(_freeze(item) for item in self.types))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "version": self.version,
            "name": self.name,
            "delivery": self.delivery,
            "state_commit": self.state_commit,
            "reentrant_reaction": self.reentrant_reaction,
            "instances": _thaw(self.instances),
            "routes": _thaw(self.routes),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "types": _thaw(self.types),
        }


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].rstrip()


def _top_level(line: str) -> bool:
    return bool(line) and not line[0].isspace()


def extract_assemblies(source: str) -> tuple[str, tuple[AssemblyDecl, ...]]:
    """Extract top-level Assembly blocks while retaining source line numbers."""

    raw_lines = source.splitlines()
    output = list(raw_lines)
    assemblies: list[AssemblyDecl] = []
    seen: dict[str, int] = {}
    i = 0

    while i < len(raw_lines):
        original = raw_lines[i]
        clean = _strip_comment(original)
        if (
            not clean.strip()
            or not _top_level(original)
            or _ASSEMBLY_PREFIX_RE.match(clean) is None
        ):
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
            if body_clean.strip() and _top_level(body_original):
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


def has_top_level_assembly(source: str) -> bool:
    for original in source.splitlines():
        clean = _strip_comment(original)
        if clean and _top_level(original) and _ASSEMBLY_PREFIX_RE.match(clean):
            return True
    return False


def _render_type(ty: TypeRef) -> str:
    if ty.name == "tuple" and not ty.args:
        return "()"
    if not ty.args:
        return ty.name
    return f"{ty.name}<{','.join(_render_type(item) for item in ty.args)}>"


def _normalized_type_name(name: str) -> str:
    return _BUILTIN_TYPE_NAMES.get(name, name)


def _type_ref_ir(ty: TypeRef) -> dict[str, object]:
    name = "()" if ty.name == "tuple" and not ty.args else (
        "Tuple" if ty.name == "tuple" else _normalized_type_name(ty.name)
    )
    return {
        "name": name,
        "arguments": tuple(_type_ref_ir(item) for item in ty.args),
    }


def _resolve_alias(ty: TypeRef, aliases: Mapping[str, TypeRef]) -> TypeRef:
    current = ty
    seen: set[str] = set()
    while not current.args and current.name in aliases and current.name not in seen:
        seen.add(current.name)
        current = aliases[current.name]
    normalized_name = (
        "()" if current.name == "tuple" and not current.args else (
            "Tuple" if current.name == "tuple" else _normalized_type_name(current.name)
        )
    )
    return TypeRef(
        normalized_name,
        tuple(_resolve_alias(item, aliases) for item in current.args),
    )


def _is_unit(ty: TypeRef, aliases: Mapping[str, TypeRef]) -> bool:
    resolved = _resolve_alias(ty, aliases)
    return resolved.name == "()" and not resolved.args


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


def _value_expressions(function: FunctionDecl) -> tuple[Expr, ...]:
    if function.expression is not None:
        return (function.expression,)
    return tuple(clause.value for clause in function.guards)


def _potentially_reachable_values(function: FunctionDecl) -> tuple[Expr, ...]:
    if function.expression is not None:
        return (function.expression,)
    result: list[Expr] = []
    for clause in function.guards:
        condition = clause.condition
        if isinstance(condition, BoolExpr) and not condition.value:
            continue
        result.append(clause.value)
        if condition is None or (isinstance(condition, BoolExpr) and condition.value):
            break
    return tuple(result)


def _reachable_effects(
    machine: MachineDecl,
    functions: Mapping[str, FunctionDecl],
    effects: Mapping[str, ExternDecl],
    inline_effects: Mapping[str, FunctionDecl],
) -> set[str]:
    """Conservative fallback used when normalized Action reachability is unavailable."""

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
            implementation = inline_effects.get(name)
            if implementation is not None:
                for expression in _potentially_reachable_values(implementation):
                    pending.extend(_direct_calls(expression))
            continue
        function = functions.get(name)
        if function is None:
            continue
        for expression in _potentially_reachable_values(function):
            pending.extend(_direct_calls(expression))

    return reachable


def _type_definitions(program: Program) -> tuple[dict[str, object], ...]:
    result: list[dict[str, object]] = []
    for declaration in program.declarations:
        if isinstance(declaration, ProductDecl):
            result.append(
                {
                    "name": declaration.name,
                    "kind": "product",
                    "fields": tuple(
                        {
                            "name": field.name,
                            "type": _type_ref_ir(field.ty),
                        }
                        for field in declaration.fields
                    ),
                }
            )
        elif isinstance(declaration, SumDecl):
            result.append(
                {
                    "name": declaration.name,
                    "kind": "sum",
                    "variants": tuple(
                        {
                            "name": variant.name,
                            "tuple_types": tuple(
                                _type_ref_ir(item) for item in variant.tuple_types
                            ),
                            "fields": tuple(
                                {
                                    "name": field.name,
                                    "type": _type_ref_ir(field.ty),
                                }
                                for field in variant.fields
                            ),
                        }
                        for variant in declaration.variants
                    ),
                }
            )
        elif isinstance(declaration, AliasDecl):
            result.append(
                {
                    "name": declaration.name,
                    "kind": "alias",
                    "target": _type_ref_ir(declaration.target),
                }
            )
    return tuple(result)


def _effect_signature(effect: ExternDecl) -> dict[str, object]:
    return {
        "name": effect.name,
        "parameters": tuple(
            {
                "name": parameter.name,
                "type": _render_type(parameter.ty),
                "type_ref": _type_ref_ir(parameter.ty),
            }
            for parameter in effect.params
        ),
        "result_type": _render_type(effect.return_type),
        "result_type_ref": _type_ref_ir(effect.return_type),
    }


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
                        + "。実際に循環が発火すると再入エラーになる"
                    ),
                    line=route_lines.get(edge, assembly.line),
                )
            )
            return
        if node in visited:
            return
        visiting.add(node)
        for target in sorted(adjacency.get(node, ())):
            visit(target, (*path, node))
        visiting.remove(node)
        visited.add(node)

    for instance in sorted(adjacency):
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
    inline_effects: Sequence[FunctionDecl] = (),
    reachable_actions_by_machine: Mapping[str, set[str]] | None = None,
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
    inline_effect_by_name = {effect.name: effect for effect in inline_effects}
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

        reachable_by_instance: dict[str, set[str]] = {}
        for instance_name, machine in instance_machine.items():
            if reachable_actions_by_machine is not None:
                reachable_by_instance[instance_name] = set(
                    reachable_actions_by_machine.get(machine.name, set())
                )
            else:
                reachable_by_instance[instance_name] = _reachable_effects(
                    machine,
                    functions,
                    effects,
                    inline_effect_by_name,
                )

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
            if route.effect in inline_effect_by_name:
                raise GlyphError(
                    f"{route.line}行目: 内部route化する !effect '{route.effect}' は"
                    "Host試作本体を持てない。宣言だけにする"
                )
            if len(effect.params) != 1:
                raise GlyphError(
                    f"{route.line}行目: v1の内部route effect '{route.effect}' は"
                    "payload引数を1つだけ持つ必要がある"
                )
            if not _is_unit(effect.return_type, aliases):
                raise GlyphError(
                    f"{route.line}行目: 内部route effect '{route.effect}' の戻り値は()が必要。"
                    "route payloadは戻り値ではなく引数から渡す"
                )
            if route.effect not in reachable_by_instance[route.source_instance]:
                raise GlyphError(
                    f"{route.line}行目: effect '{route.effect}' はMachine "
                    f"'{source.machine}' の到達可能な遷移Actionから到達できない"
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
            if len(target_machine.input_params) != 1:
                raise GlyphError(
                    f"{route.line}行目: v1の即時route先Machine '{target.machine}' は"
                    "入力parameterを1つだけ持つ必要がある"
                )
            target_param = target_machine.input_params[0]
            if target_param.name != route.input:
                raise GlyphError(
                    f"{route.line}行目: Machine '{target.machine}' に入力 '{route.input}' がない"
                    f"。使用可能: {target_param.name}"
                )

            payload_param = effect.params[0]
            source_type = _resolve_alias(payload_param.ty, aliases)
            target_type = _resolve_alias(target_param.ty, aliases)
            if source_type != target_type:
                raise GlyphError(
                    f"{route.line}行目: route型不一致: "
                    f"{route.source_instance}.{route.effect} の引数は "
                    f"{_render_type(payload_param.ty)}、"
                    f"{route.target_instance}.{route.input} は {_render_type(target_param.ty)}"
                )

            route_ir.append(
                {
                    "source_instance": route.source_instance,
                    "source_machine": source.machine,
                    "effect": route.effect,
                    "payload_parameter": payload_param.name,
                    "payload_type": _render_type(payload_param.ty),
                    "payload_type_ref": _type_ref_ir(payload_param.ty),
                    "result_type": "()",
                    "result_type_ref": {"name": "()", "arguments": ()},
                    "target_instance": route.target_instance,
                    "target_machine": target.machine,
                    "input": route.input,
                    "delivery": "immediate",
                    "order": order,
                    "line": route.line,
                }
            )

        instance_ir: list[dict[str, object]] = []
        for item in assembly.instances:
            machine = instance_machine[item.name]
            allowed_names = tuple(sorted(reachable_by_instance[item.name]))
            instance_ir.append(
                {
                    "name": item.name,
                    "machine": item.machine,
                    "line": item.line,
                    "state": {
                        "parameter": machine.state_param.name,
                        "type": _render_type(machine.state_param.ty),
                        "type_ref": _type_ref_ir(machine.state_param.ty),
                        "initial_expression": repr(machine.initial),
                    },
                    "inputs": tuple(
                        {
                            "name": param.name,
                            "type": _render_type(param.ty),
                            "type_ref": _type_ref_ir(param.ty),
                        }
                        for param in machine.input_params
                    ),
                    "allowed_effects": allowed_names,
                    "effects": tuple(
                        _effect_signature(effects[name])
                        for name in allowed_names
                        if name in effects
                    ),
                }
            )

        result.append(
            MachineAssemblyIR(
                schema="glyph.machine-assembly-ir",
                version=2,
                name=assembly.name,
                delivery="immediate-call-point",
                state_commit="atomic-per-top-level-reaction",
                reentrant_reaction="forbidden",
                instances=tuple(instance_ir),
                routes=tuple(route_ir),
                diagnostics=_cycle_diagnostics(assembly),
                types=_type_definitions(program),
            )
        )

    return tuple(result)

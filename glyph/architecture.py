from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

from .compiler import (
    AliasDecl,
    BinaryExpr,
    CallExpr,
    ExternDecl,
    Expr,
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
from .schema import ARCHITECTURE_IR_SCHEMA, versioned_payload


@dataclass(frozen=True)
class SystemEdgeDecl:
    """One checked system-context flow assertion."""

    source_name: str
    target_name: str
    line: int


@dataclass(frozen=True)
class SystemPortDecl:
    """A typed public input or output of one system boundary."""

    name: str
    direction: str
    type_text: str
    line: int


@dataclass(frozen=True)
class SystemDecl:
    """Human-readable system boundary checked against the complete program.

    Canonical syntax is::

        system DoorController
          entry control
          in state:DoorState
          in sensor:Input
          out receipt:Receipt
          state -> control
          sensor -> control
          control -> receipt
          control -> lock
          control -> alarm

    The system block does not create executable calls. Each edge is accepted only
    when the compiler can attach typed code evidence. `system Name=entry` is
    intentionally rejected; the entry is an explicit indented declaration so the
    boundary remains readable before the implementation body.
    """

    name: str
    entry_name: str
    ports: tuple[SystemPortDecl, ...]
    edges: tuple[SystemEdgeDecl, ...]
    external_names: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class ArchitecturePort:
    id: str
    name: str
    direction: str
    type: str
    binding: str | None
    line: int


@dataclass(frozen=True)
class ArchitectureComponent:
    id: str
    name: str
    kind: str
    binding: str | None
    line: int


@dataclass(frozen=True)
class ArchitectureEvidence:
    id: str
    kind: str
    path: tuple[str, ...]
    payload_type: str | None
    line: int


@dataclass(frozen=True)
class ArchitectureEdge:
    source_id: str
    target_id: str
    line: int
    kind: str
    payload_type: str | None
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ArchitectureSystem:
    id: str
    name: str
    entry: str
    ports: tuple[ArchitecturePort, ...]
    components: tuple[ArchitectureComponent, ...]
    edges: tuple[ArchitectureEdge, ...]
    evidence: tuple[ArchitectureEvidence, ...]
    line: int


@dataclass(frozen=True)
class ArchitectureIR:
    source_name: str
    systems: tuple[ArchitectureSystem, ...]

    def to_dict(self) -> dict[str, object]:
        return versioned_payload(ARCHITECTURE_IR_SCHEMA, asdict(self))


def _safe_id(text: str) -> str:
    value = "".join(char if char.isalnum() or char == "_" else "_" for char in text)
    return value or "component"


def _code_and_comment(line: str) -> tuple[str, str]:
    marker = line.find("#")
    if marker < 0:
        return line.rstrip(), ""
    return line[:marker].rstrip(), line[marker:]


def _external_name(text: str, line: int) -> str:
    signature = text[len("ext") :].strip()
    open_pos = signature.find("(")
    if open_pos <= 0:
        raise GlyphError(f"{line}行目: ext name(args):Type の形式が必要")
    name = signature[:open_pos].strip()
    if not name.isidentifier():
        raise GlyphError(f"{line}行目: ext名が不正: '{name}'")
    if "=" in signature:
        raise GlyphError(
            f"{line}行目: ext '{name}' は外部契約なのでGlyph本体を書けない"
        )
    return name


def _mask_external_declarations(
    lines: Sequence[str], output: list[str]
) -> tuple[str, ...]:
    names: list[str] = []
    seen: dict[str, int] = {}
    for index, original in enumerate(lines):
        code, comment = _code_and_comment(original)
        stripped = code.strip()
        if not stripped or code[:1].isspace() or not stripped.startswith("ext "):
            continue
        line = index + 1
        name = _external_name(stripped, line)
        if name in seen:
            raise GlyphError(
                f"{line}行目: ext '{name}' は{seen[name]}行目で定義済み"
            )
        seen[name] = line
        names.append(name)
        signature = stripped[len("ext") :].strip()
        output[index] = f"!{signature}" + ((" " + comment) if comment else "")
    return tuple(names)


def _parse_port(text: str, direction: str, line: int) -> SystemPortDecl:
    payload = text[len(direction) :].strip()
    if payload.count(":") != 1:
        raise GlyphError(
            f"{line}行目: system {direction} portは `{direction} name:Type` の形式にする"
        )
    name, type_text = (part.strip() for part in payload.split(":", 1))
    if not name.isidentifier():
        raise GlyphError(f"{line}行目: system port名が不正: '{name}'")
    if not type_text:
        raise GlyphError(f"{line}行目: system port '{name}' の型が必要")
    return SystemPortDecl(name, "input" if direction == "in" else "output", type_text, line)


def extract_systems(source: str) -> tuple[str, tuple[SystemDecl, ...]]:
    """Extract checked system-context declarations and explicit `ext` contracts."""

    lines = source.splitlines()
    output = list(lines)
    external_names = _mask_external_declarations(lines, output)
    systems: list[SystemDecl] = []
    seen_names: dict[str, int] = {}
    index = 0
    while index < len(lines):
        original = lines[index]
        clean = original.split("#", 1)[0].rstrip()
        stripped = clean.strip()
        if clean[:1].isspace() or not stripped.startswith("system "):
            index += 1
            continue

        line = index + 1
        header = stripped[len("system ") :].strip()
        if "=" in header:
            name = header.split("=", 1)[0].strip() or "Name"
            raise GlyphError(
                f"{line}行目: `system Name=entry` は廃止された。次の形式へ移行する:\n"
                f"system {name}\n  entry entry_name"
            )
        name = header
        if not name.isidentifier():
            raise GlyphError(f"{line}行目: system名が不正: '{name}'")
        if name in seen_names:
            raise GlyphError(
                f"{line}行目: system '{name}' は{seen_names[name]}行目で定義済み"
            )
        seen_names[name] = line
        output[index] = ""

        entry_name: str | None = None
        ports: list[SystemPortDecl] = []
        assertions: list[SystemEdgeDecl] = []
        seen_ports: dict[str, int] = {}
        seen_edges: set[tuple[str, str]] = set()
        cursor = index + 1
        while cursor < len(lines):
            item_original = lines[cursor]
            item_clean = item_original.split("#", 1)[0].rstrip()
            if not item_clean.strip():
                cursor += 1
                continue
            if not item_clean[:1].isspace():
                break
            item_line = cursor + 1
            item = item_clean.strip()
            output[cursor] = ""

            if item.startswith("entry "):
                candidate = item[len("entry ") :].strip()
                if not candidate.isidentifier():
                    raise GlyphError(
                        f"{item_line}行目: system entry名が不正: '{candidate}'"
                    )
                if entry_name is not None:
                    raise GlyphError(
                        f"{item_line}行目: system '{name}' のentryは一つだけ宣言する"
                    )
                entry_name = candidate
                cursor += 1
                continue

            if item.startswith("in "):
                port = _parse_port(item, "in", item_line)
                if port.name in seen_ports:
                    raise GlyphError(
                        f"{item_line}行目: system port '{port.name}' は"
                        f"{seen_ports[port.name]}行目で宣言済み"
                    )
                seen_ports[port.name] = item_line
                ports.append(port)
                cursor += 1
                continue

            if item.startswith("out "):
                port = _parse_port(item, "out", item_line)
                if port.name in seen_ports:
                    raise GlyphError(
                        f"{item_line}行目: system port '{port.name}' は"
                        f"{seen_ports[port.name]}行目で宣言済み"
                    )
                seen_ports[port.name] = item_line
                ports.append(port)
                cursor += 1
                continue

            if item.count("->") != 1:
                raise GlyphError(
                    f"{item_line}行目: system itemは `entry name`, `in name:Type`, "
                    "`out name:Type`, または `source -> target` の形式にする"
                )
            source_name, target_name = (
                part.strip() for part in item.split("->", 1)
            )
            if not source_name.isidentifier() or not target_name.isidentifier():
                raise GlyphError(
                    f"{item_line}行目: system endpoint名は識別子にする: {item}"
                )
            if source_name == target_name:
                raise GlyphError(
                    f"{item_line}行目: self-edge '{item}' は書けない"
                )
            pair = (source_name, target_name)
            if pair in seen_edges:
                raise GlyphError(
                    f"{item_line}行目: system edge '{item}' が重複"
                )
            seen_edges.add(pair)
            assertions.append(SystemEdgeDecl(source_name, target_name, item_line))
            cursor += 1

        if entry_name is None:
            raise GlyphError(
                f"{line}行目: system '{name}' には `entry function_name` が必要"
            )
        if not any(port.direction == "input" for port in ports):
            raise GlyphError(f"{line}行目: system '{name}' には少なくとも一つのin portが必要")
        if not any(port.direction == "output" for port in ports):
            raise GlyphError(f"{line}行目: system '{name}' には少なくとも一つのout portが必要")
        if not assertions:
            raise GlyphError(
                f"{line}行目: system '{name}' には境界flow edgeが必要"
            )

        systems.append(
            SystemDecl(
                name,
                entry_name,
                tuple(ports),
                tuple(assertions),
                external_names,
                line,
            )
        )
        index = cursor

    return (
        "\n".join(output) + ("\n" if source.endswith("\n") else ""),
        tuple(systems),
    )


def _walk_calls(expr: Expr) -> Iterable[str]:
    if isinstance(expr, CallExpr):
        if isinstance(expr.callee, NameExpr):
            yield expr.callee.name
        else:
            yield from _walk_calls(expr.callee)
        for argument in expr.args:
            yield from _walk_calls(argument)
    elif isinstance(expr, UnaryExpr):
        yield from _walk_calls(expr.expr)
    elif isinstance(expr, TryExpr):
        yield from _walk_calls(expr.expr)
    elif isinstance(expr, BinaryExpr):
        yield from _walk_calls(expr.left)
        yield from _walk_calls(expr.right)
    elif isinstance(expr, FieldExpr):
        yield from _walk_calls(expr.base)


def _function_calls(declaration: FunctionDecl) -> tuple[tuple[str, int], ...]:
    rows: list[tuple[str, int]] = []
    if declaration.expression is not None:
        rows.extend((name, declaration.line) for name in _walk_calls(declaration.expression))
    for clause in declaration.guards:
        if clause.condition is not None:
            rows.extend((name, clause.line) for name in _walk_calls(clause.condition))
        rows.extend((name, clause.line) for name in _walk_calls(clause.value))
    return tuple(rows)


def _known_non_callable_names(program: Program) -> set[str]:
    names = {"Ok", "Err", "Some", "min", "max", "finite"}
    for declaration in program.declarations:
        if isinstance(declaration, ProductDecl):
            names.add(declaration.name)
        elif isinstance(declaration, SumDecl):
            names.update(variant.name for variant in declaration.variants)
        elif isinstance(declaration, AliasDecl):
            names.add(declaration.name)
    return names


def _callable_bindings(
    program: Program, external_names: set[str]
) -> dict[str, tuple[str, FunctionDecl | ExternDecl]]:
    bindings: dict[str, tuple[str, FunctionDecl | ExternDecl]] = {}
    for declaration in program.declarations:
        if isinstance(declaration, FunctionDecl):
            bindings[declaration.name] = ("function", declaration)
        elif isinstance(declaration, ExternDecl):
            kind = "external" if declaration.name in external_names else "effect"
            bindings[declaration.name] = (kind, declaration)
    return bindings


def _visible_calls(
    declaration: FunctionDecl,
    functions: dict[str, FunctionDecl],
    bindings: dict[str, tuple[str, FunctionDecl | ExternDecl]],
    known_non_callable: set[str],
    *,
    system_name: str,
    expanding: tuple[str, ...] = (),
) -> tuple[tuple[str, int], ...]:
    """Flatten compiler-generated helper calls while retaining user declarations."""

    output: list[tuple[str, int]] = []
    for callee, line in _function_calls(declaration):
        if callee in known_non_callable:
            continue
        if callee.startswith("__glyph_") and callee in functions:
            if callee in expanding:
                continue
            output.extend(
                _visible_calls(
                    functions[callee],
                    functions,
                    bindings,
                    known_non_callable,
                    system_name=system_name,
                    expanding=(*expanding, callee),
                )
            )
            continue
        if callee not in bindings:
            raise GlyphError(
                f"{line}行目: system '{system_name}' が到達する呼出し '{callee}' は"
                "宣言されていない。外部入力なら `ext name(args):Type` で宣言する"
            )
        output.append((callee, line))
    return tuple(output)


_PRIMITIVE_TYPES = {
    "B": "bool",
    "F": "f32",
    "I": "i16",
    "S": "String",
    "U": "u16",
    "F32": "f32",
    "F64": "f64",
    "I8": "i8",
    "I16": "i16",
    "I32": "i32",
    "I64": "i64",
    "U8": "u8",
    "U16": "u16",
    "U32": "u32",
    "U64": "u64",
}


def _canonical_type_ref(ty: TypeRef) -> str:
    if ty.name in {"Result", "R"} and len(ty.args) == 2:
        return f"{_canonical_type_ref(ty.args[0])}|{_canonical_type_ref(ty.args[1])}"
    name = _PRIMITIVE_TYPES.get(ty.name, ty.name)
    if not ty.args:
        return name
    return f"{name}<{','.join(_canonical_type_ref(arg) for arg in ty.args)}>"


def _canonical_type_text(text: str) -> str:
    compact = "".join(text.split())
    return _PRIMITIVE_TYPES.get(compact, compact)


def _success_type(ty: TypeRef) -> str:
    if ty.name in {"Result", "R"} and len(ty.args) == 2:
        return _canonical_type_ref(ty.args[0])
    return _canonical_type_ref(ty)


def _direct_graph(
    functions: dict[str, FunctionDecl],
    bindings: dict[str, tuple[str, FunctionDecl | ExternDecl]],
    known_non_callable: set[str],
    system_name: str,
) -> dict[str, tuple[str, ...]]:
    graph: dict[str, tuple[str, ...]] = {}
    for name, declaration in functions.items():
        visible = _visible_calls(
            declaration,
            functions,
            bindings,
            known_non_callable,
            system_name=system_name,
            expanding=(name,),
        )
        ordered: list[str] = []
        for target, _ in visible:
            if target not in ordered:
                ordered.append(target)
        graph[name] = tuple(ordered)
    return graph


def _path(graph: dict[str, tuple[str, ...]], source: str, target: str) -> tuple[str, ...] | None:
    if source == target:
        return (source,)
    queue: deque[tuple[str, ...]] = deque([(source,)])
    visited = {source}
    while queue:
        current = queue.popleft()
        for candidate in graph.get(current[-1], ()):
            if candidate == target:
                return (*current, candidate)
            if candidate in visited or candidate not in graph:
                continue
            visited.add(candidate)
            queue.append((*current, candidate))
    return None


def _reachable(graph: dict[str, tuple[str, ...]], entry: str) -> tuple[str, ...]:
    output: list[str] = []
    queue = deque([entry])
    seen = {entry}
    while queue:
        current = queue.popleft()
        output.append(current)
        for target in graph.get(current, ()):
            if target in seen:
                continue
            seen.add(target)
            queue.append(target)
    return tuple(output)


def _parameter_matches(function: FunctionDecl, port: SystemPortDecl) -> bool:
    expected = _canonical_type_text(port.type_text)
    return any(
        parameter.name == port.name
        and _canonical_type_ref(parameter.ty) == expected
        for parameter in function.params
    )


def _validate_effect_exclusivity(
    declaration: FunctionDecl,
    effect_names: set[str],
) -> None:
    for clause in declaration.guards:
        selected = [name for name in _walk_calls(clause.value) if name in effect_names]
        if len(set(selected)) > 1:
            raise GlyphError(
                f"{clause.line}行目: guard branchが複数effect "
                f"{sorted(set(selected))} を実行する。作用は一経路につき一つにする"
            )


def build_architecture_ir(
    source_name: str, program: Program, systems: Sequence[SystemDecl]
) -> ArchitectureIR:
    external_names = {name for system in systems for name in system.external_names}
    bindings = _callable_bindings(program, external_names)
    known_non_callable = _known_non_callable_names(program)
    functions = {
        name: declaration
        for name, (_, declaration) in bindings.items()
        if isinstance(declaration, FunctionDecl)
    }
    effect_names = {name for name, (kind, _) in bindings.items() if kind == "effect"}

    resolved_systems: list[ArchitectureSystem] = []
    for system_index, system in enumerate(systems):
        entry_binding = bindings.get(system.entry_name)
        if entry_binding is None:
            raise GlyphError(
                f"{system.line}行目: system '{system.name}' のentry "
                f"'{system.entry_name}' は未宣言"
            )
        if entry_binding[0] != "function":
            raise GlyphError(
                f"{system.line}行目: system entry '{system.entry_name}' は"
                "本体を持つ `>` 関数にする"
            )
        entry_decl = entry_binding[1]
        assert isinstance(entry_decl, FunctionDecl)

        graph = _direct_graph(functions, bindings, known_non_callable, system.name)
        reachable_names = set(_reachable(graph, system.entry_name))

        ports_by_name = {port.name: port for port in system.ports}
        for edge in system.edges:
            for endpoint in (edge.source_name, edge.target_name):
                if endpoint not in ports_by_name and endpoint not in bindings:
                    raise GlyphError(
                        f"{edge.line}行目: system '{system.name}' endpoint "
                        f"'{endpoint}' は未宣言。外部入力なら `ext {endpoint}(...):Type` "
                        "と対応する `in` portを宣言する"
                    )

        output_ports = [port for port in system.ports if port.direction == "output"]
        if len(output_ports) != 1:
            raise GlyphError(
                f"{system.line}行目: R1ではsystem output portを一つだけ宣言する"
            )
        output_port = output_ports[0]
        expected_output = _canonical_type_text(output_port.type_text)
        actual_output = _success_type(entry_decl.return_type)
        if actual_output != expected_output:
            raise GlyphError(
                f"{output_port.line}行目: output port '{output_port.name}' は"
                f"{expected_output}だがentry '{system.entry_name}' の正常戻り型は"
                f"{actual_output}"
            )

        for name in reachable_names:
            declaration = functions.get(name)
            if declaration is not None:
                _validate_effect_exclusivity(declaration, effect_names)

        local_ids: dict[str, str] = {}
        components: list[ArchitectureComponent] = []
        ports: list[ArchitecturePort] = []

        endpoint_order: list[str] = []
        for port in system.ports:
            if port.name not in endpoint_order:
                endpoint_order.append(port.name)
        if system.entry_name not in endpoint_order:
            endpoint_order.append(system.entry_name)
        for edge in system.edges:
            for endpoint in (edge.source_name, edge.target_name):
                if endpoint not in endpoint_order:
                    endpoint_order.append(endpoint)

        for endpoint_index, name in enumerate(endpoint_order):
            port = ports_by_name.get(name)
            binding = bindings.get(name)
            local_id = f"arch_{system_index}_{endpoint_index}_{_safe_id(name)}"
            local_ids[name] = local_id
            if port is not None:
                bound_name = name if binding is not None else None
                ports.append(
                    ArchitecturePort(
                        local_id,
                        name,
                        port.direction,
                        _canonical_type_text(port.type_text),
                        bound_name,
                        port.line,
                    )
                )
            if binding is not None:
                kind, declaration = binding
                component_kind = (
                    "external" if kind == "external" else
                    "effect" if kind == "effect" else
                    "function"
                )
                components.append(
                    ArchitectureComponent(
                        local_id, name, component_kind, name, declaration.line
                    )
                )
            elif port is not None:
                components.append(
                    ArchitectureComponent(
                        local_id,
                        name,
                        ("external" if port.direction == "input" else "data"),
                        None,
                        port.line,
                    )
                )

        evidence: list[ArchitectureEvidence] = []
        edges: list[ArchitectureEdge] = []
        covered_external: set[str] = set()
        covered_effects: set[str] = set()
        output_edge_seen = False

        def add_evidence(
            kind: str,
            path_value: tuple[str, ...],
            payload_type: str | None,
            line: int,
        ) -> str:
            evidence_id = f"evidence_{system_index}_{len(evidence)}_{_safe_id(kind)}"
            evidence.append(
                ArchitectureEvidence(
                    evidence_id, kind, path_value, payload_type, line
                )
            )
            return evidence_id

        for edge in system.edges:
            source_port = ports_by_name.get(edge.source_name)
            target_port = ports_by_name.get(edge.target_name)
            source_binding = bindings.get(edge.source_name)
            target_binding = bindings.get(edge.target_name)
            edge_kind: str
            payload_type: str | None
            evidence_ids: list[str] = []

            if source_port is not None and source_port.direction == "input":
                payload_type = _canonical_type_text(source_port.type_text)
                if source_binding is not None:
                    if source_binding[0] != "external":
                        raise GlyphError(
                            f"{edge.line}行目: input port '{edge.source_name}' と同名の"
                            "symbolはext境界でなければならない"
                        )
                    ext_decl = source_binding[1]
                    assert isinstance(ext_decl, ExternDecl)
                    actual = _success_type(ext_decl.return_type)
                    if actual != payload_type:
                        raise GlyphError(
                            f"{source_port.line}行目: input port '{source_port.name}' は"
                            f"{payload_type}だがext境界の正常戻り型は{actual}"
                        )
                    if target_binding is None or target_binding[0] != "function":
                        raise GlyphError(
                            f"{edge.line}行目: external inputの接続先"
                            f"'{edge.target_name}' は関数にする"
                        )
                    path_value = _path(graph, edge.target_name, edge.source_name)
                    if path_value is None:
                        raise GlyphError(
                            f"{edge.line}行目: system edge "
                            f"'{edge.source_name} -> {edge.target_name}' を裏付ける"
                            "external input readがコードに存在しない"
                        )
                    evidence_ids.append(
                        add_evidence("external-input-read", path_value, payload_type, edge.line)
                    )
                    covered_external.add(edge.source_name)
                else:
                    if edge.target_name != system.entry_name:
                        raise GlyphError(
                            f"{edge.line}行目: caller input port '{edge.source_name}' は"
                            "entryへ接続する"
                        )
                    if not _parameter_matches(entry_decl, source_port):
                        raise GlyphError(
                            f"{edge.line}行目: input port '{edge.source_name}:{payload_type}' "
                            f"に対応するentry parameterが存在しない"
                        )
                    evidence_ids.append(
                        add_evidence(
                            "entry-parameter",
                            (edge.source_name, system.entry_name),
                            payload_type,
                            edge.line,
                        )
                    )
                edge_kind = "data"

            elif target_port is not None and target_port.direction == "output":
                if source_binding is None or source_binding[0] != "function":
                    raise GlyphError(
                        f"{edge.line}行目: output portのsource '{edge.source_name}' は"
                        "関数にする"
                    )
                source_decl = source_binding[1]
                assert isinstance(source_decl, FunctionDecl)
                payload_type = _canonical_type_text(target_port.type_text)
                if _success_type(source_decl.return_type) != payload_type:
                    raise GlyphError(
                        f"{edge.line}行目: '{edge.source_name}' の正常戻り型は"
                        f"output port '{edge.target_name}:{payload_type}' と一致しない"
                    )
                if edge.source_name != system.entry_name:
                    path_value = _path(graph, system.entry_name, edge.source_name)
                    if path_value is None:
                        raise GlyphError(
                            f"{edge.line}行目: output source '{edge.source_name}' は"
                            "entryから到達不能"
                        )
                else:
                    path_value = (system.entry_name,)
                evidence_ids.append(
                    add_evidence("return-type", path_value, payload_type, edge.line)
                )
                edge_kind = "return"
                output_edge_seen = True

            elif source_binding is not None and target_binding is not None:
                if source_binding[0] != "function":
                    raise GlyphError(
                        f"{edge.line}行目: system internal/effect edgeのsource "
                        f"'{edge.source_name}' は関数にする"
                    )
                path_value = _path(graph, edge.source_name, edge.target_name)
                if path_value is None:
                    raise GlyphError(
                        f"{edge.line}行目: system edge "
                        f"'{edge.source_name} -> {edge.target_name}' を裏付ける"
                        "到達可能なコードpathが存在しない"
                    )
                if target_binding[0] == "effect":
                    target_decl = target_binding[1]
                    assert isinstance(target_decl, ExternDecl)
                    payload_type = (
                        _canonical_type_ref(target_decl.params[0].ty)
                        if target_decl.params else None
                    )
                    edge_kind = "effect"
                    covered_effects.add(edge.target_name)
                    evidence_kind = "effect-reachability"
                elif target_binding[0] == "external":
                    raise GlyphError(
                        f"{edge.line}行目: ext境界 '{edge.target_name}' は"
                        "system入力側から内部へ接続する"
                    )
                else:
                    payload_type = None
                    edge_kind = "responsibility"
                    evidence_kind = "call-path"
                evidence_ids.append(
                    add_evidence(evidence_kind, path_value, payload_type, edge.line)
                )
            else:
                raise GlyphError(
                    f"{edge.line}行目: system edge "
                    f"'{edge.source_name} -> {edge.target_name}' の極性を解決できない"
                )

            edges.append(
                ArchitectureEdge(
                    local_ids[edge.source_name],
                    local_ids[edge.target_name],
                    edge.line,
                    edge_kind,
                    payload_type,
                    tuple(evidence_ids),
                )
            )

        reachable_external = {
            name for name in reachable_names if bindings.get(name, (None,))[0] == "external"
        }
        reachable_effects = {
            name for name in reachable_names if bindings.get(name, (None,))[0] == "effect"
        }
        missing_external = sorted(reachable_external - covered_external)
        missing_effects = sorted(reachable_effects - covered_effects)
        if missing_external:
            raise GlyphError(
                f"{system.line}行目: system '{system.name}' はentryから利用する外部入力 "
                f"{missing_external} をin portとflow edgeで公開していない"
            )
        if missing_effects:
            raise GlyphError(
                f"{system.line}行目: system '{system.name}' はentryから到達する作用境界 "
                f"{missing_effects} をsystem edgeで公開していない"
            )
        if not output_edge_seen:
            raise GlyphError(
                f"{system.line}行目: system '{system.name}' はentryからout portへの"
                "return edgeを宣言していない"
            )

        resolved_systems.append(
            ArchitectureSystem(
                f"system_{system_index}_{_safe_id(system.name)}",
                system.name,
                system.entry_name,
                tuple(ports),
                tuple(components),
                tuple(edges),
                tuple(evidence),
                system.line,
            )
        )

    return ArchitectureIR(source_name, tuple(resolved_systems))

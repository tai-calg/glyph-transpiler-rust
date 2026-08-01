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
    """Deprecated system flow assertion retained for source compatibility."""

    source_name: str
    target_name: str
    line: int


@dataclass(frozen=True)
class SystemPortDecl:
    """Deprecated system value port retained for source compatibility."""

    name: str
    direction: str
    type_text: str
    line: int


@dataclass(frozen=True)
class SystemDecl:
    """A complete executable system boundary.

    Canonical syntax is::

        system DoorController
          entry control
          source sensor
          sink lock
          sink alarm

    ``entry`` names the Glyph function invoked from outside the system.
    ``source`` names an ``ext`` function that the system calls to pull input.
    ``sink`` names a ``!`` function that the system calls to cause an external
    effect. Values and types are derived from the function signatures and are
    never redeclared in the system block.

    Legacy ``in``, ``out`` and ``a -> b`` items are parsed only so existing
    source files can be migrated without losing data. They no longer define the
    architecture graph; the graph is always derived from executable calls.
    """

    name: str
    entry_name: str
    source_names: tuple[str, ...]
    sink_names: tuple[str, ...]
    external_names: tuple[str, ...]
    line: int
    ports: tuple[SystemPortDecl, ...] = ()
    edges: tuple[SystemEdgeDecl, ...] = ()
    syntax: str = "entry-source-sink"


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
    role: str | None = None


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
    sources: tuple[str, ...] = ()
    sinks: tuple[str, ...] = ()


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


def _boundary_name(item: str, keyword: str, line: int) -> str:
    candidate = item[len(keyword) :].strip()
    if not candidate.isidentifier():
        raise GlyphError(
            f"{line}行目: system {keyword}名が不正: '{candidate}'"
        )
    return candidate


def _parse_legacy_port(text: str, direction: str, line: int) -> SystemPortDecl:
    payload = text[len(direction) :].strip()
    if payload.count(":") != 1:
        raise GlyphError(
            f"{line}行目: system {direction} portは "
            f"`{direction} name:Type` の形式にする"
        )
    name, type_text = (part.strip() for part in payload.split(":", 1))
    if not name.isidentifier():
        raise GlyphError(f"{line}行目: system port名が不正: '{name}'")
    if not type_text:
        raise GlyphError(f"{line}行目: system port '{name}' の型が必要")
    return SystemPortDecl(
        name,
        "input" if direction == "in" else "output",
        type_text,
        line,
    )


def extract_systems(source: str) -> tuple[str, tuple[SystemDecl, ...]]:
    """Extract ``entry/source/sink`` boundaries and explicit ``ext`` contracts."""

    lines = source.splitlines()
    output = list(lines)
    external_names = _mask_external_declarations(lines, output)
    systems: list[SystemDecl] = []
    seen_systems: dict[str, int] = {}
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
        if name in seen_systems:
            raise GlyphError(
                f"{line}行目: system '{name}' は"
                f"{seen_systems[name]}行目で定義済み"
            )
        seen_systems[name] = line
        output[index] = ""

        entry_name: str | None = None
        sources: list[str] = []
        sinks: list[str] = []
        legacy_ports: list[SystemPortDecl] = []
        legacy_edges: list[SystemEdgeDecl] = []
        seen_roles: dict[str, tuple[str, int]] = {}
        syntax = "entry-source-sink"

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
                candidate = _boundary_name(item, "entry", item_line)
                if entry_name is not None:
                    raise GlyphError(
                        f"{item_line}行目: system '{name}' のentryは一つだけ宣言する"
                    )
                if candidate in seen_roles:
                    previous_role, previous_line = seen_roles[candidate]
                    raise GlyphError(
                        f"{item_line}行目: '{candidate}' は{previous_line}行目で"
                        f"{previous_role}として宣言済み"
                    )
                entry_name = candidate
                seen_roles[candidate] = ("entry", item_line)
                cursor += 1
                continue

            if item.startswith("source "):
                candidate = _boundary_name(item, "source", item_line)
                if candidate in seen_roles:
                    previous_role, previous_line = seen_roles[candidate]
                    raise GlyphError(
                        f"{item_line}行目: '{candidate}' は{previous_line}行目で"
                        f"{previous_role}として宣言済み"
                    )
                sources.append(candidate)
                seen_roles[candidate] = ("source", item_line)
                cursor += 1
                continue

            if item.startswith("sink "):
                candidate = _boundary_name(item, "sink", item_line)
                if candidate in seen_roles:
                    previous_role, previous_line = seen_roles[candidate]
                    raise GlyphError(
                        f"{item_line}行目: '{candidate}' は{previous_line}行目で"
                        f"{previous_role}として宣言済み"
                    )
                sinks.append(candidate)
                seen_roles[candidate] = ("sink", item_line)
                cursor += 1
                continue

            if item.startswith("in "):
                syntax = "legacy-flow"
                legacy_ports.append(_parse_legacy_port(item, "in", item_line))
                cursor += 1
                continue
            if item.startswith("out "):
                syntax = "legacy-flow"
                legacy_ports.append(_parse_legacy_port(item, "out", item_line))
                cursor += 1
                continue
            if item.count("->") == 1:
                syntax = "legacy-flow"
                source_name, target_name = (
                    part.strip() for part in item.split("->", 1)
                )
                if not source_name.isidentifier() or not target_name.isidentifier():
                    raise GlyphError(
                        f"{item_line}行目: system endpoint名は識別子にする: {item}"
                    )
                legacy_edges.append(
                    SystemEdgeDecl(source_name, target_name, item_line)
                )
                cursor += 1
                continue

            raise GlyphError(
                f"{item_line}行目: system itemは `entry name`, "
                "`source name`, `sink name` のいずれかにする"
            )

        if entry_name is None:
            raise GlyphError(
                f"{line}行目: system '{name}' には `entry function_name` が必要"
            )
        if syntax == "legacy-flow" and (sources or sinks):
            raise GlyphError(
                f"{line}行目: system '{name}' で新しいsource/sink記法と"
                "旧in/out/->記法を混在できない"
            )

        systems.append(
            SystemDecl(
                name=name,
                entry_name=entry_name,
                source_names=tuple(sources),
                sink_names=tuple(sinks),
                external_names=external_names,
                line=line,
                ports=tuple(legacy_ports),
                edges=tuple(legacy_edges),
                syntax=syntax,
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


def _function_calls(
    declaration: FunctionDecl,
) -> tuple[tuple[str, int], ...]:
    rows: list[tuple[str, int]] = []
    if declaration.expression is not None:
        rows.extend(
            (name, declaration.line)
            for name in _walk_calls(declaration.expression)
        )
    for clause in declaration.guards:
        if clause.condition is not None:
            rows.extend(
                (name, clause.line)
                for name in _walk_calls(clause.condition)
            )
        rows.extend(
            (name, clause.line)
            for name in _walk_calls(clause.value)
        )
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
    program: Program,
    external_names: set[str],
) -> dict[str, tuple[str, FunctionDecl | ExternDecl]]:
    bindings: dict[str, tuple[str, FunctionDecl | ExternDecl]] = {}
    for declaration in program.declarations:
        if isinstance(declaration, FunctionDecl):
            bindings[declaration.name] = ("function", declaration)
        elif isinstance(declaration, ExternDecl):
            kind = (
                "external"
                if declaration.name in external_names
                else "effect"
            )
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
    """Flatten generated helpers while retaining user-visible call boundaries."""

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
                f"{line}行目: system '{system_name}' が到達する呼出し "
                f"'{callee}' は宣言されていない。外部入力なら "
                "`ext name(args):Type` で宣言する"
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
        return (
            f"{_canonical_type_ref(ty.args[0])}|"
            f"{_canonical_type_ref(ty.args[1])}"
        )
    name = _PRIMITIVE_TYPES.get(ty.name, ty.name)
    if not ty.args:
        return name
    return f"{name}<{','.join(_canonical_type_ref(arg) for arg in ty.args)}>"


def _direct_calls(
    functions: dict[str, FunctionDecl],
    bindings: dict[str, tuple[str, FunctionDecl | ExternDecl]],
    known_non_callable: set[str],
    system_name: str,
) -> dict[str, tuple[tuple[str, int], ...]]:
    graph: dict[str, tuple[tuple[str, int], ...]] = {}
    for name, declaration in functions.items():
        visible = _visible_calls(
            declaration,
            functions,
            bindings,
            known_non_callable,
            system_name=system_name,
            expanding=(name,),
        )
        ordered: list[tuple[str, int]] = []
        seen: set[str] = set()
        for target, line in visible:
            if target in seen:
                continue
            seen.add(target)
            ordered.append((target, line))
        graph[name] = tuple(ordered)
    return graph


def _reachable_order(
    graph: dict[str, tuple[tuple[str, int], ...]],
    entry: str,
) -> tuple[str, ...]:
    output: list[str] = []
    queue = deque([entry])
    seen = {entry}
    while queue:
        current = queue.popleft()
        output.append(current)
        for target, _line in graph.get(current, ()):
            if target in seen:
                continue
            seen.add(target)
            queue.append(target)
    return tuple(output)


def _validate_effect_exclusivity(
    declaration: FunctionDecl,
    effect_names: set[str],
) -> None:
    for clause in declaration.guards:
        selected = [
            name
            for name in _walk_calls(clause.value)
            if name in effect_names
        ]
        if len(set(selected)) > 1:
            raise GlyphError(
                f"{clause.line}行目: guard branchが複数effect "
                f"{sorted(set(selected))} を実行する。作用は一経路につき一つにする"
            )


def _validate_role(
    system: SystemDecl,
    name: str,
    expected_kind: str,
    bindings: dict[str, tuple[str, FunctionDecl | ExternDecl]],
) -> None:
    binding = bindings.get(name)
    if binding is None:
        keyword = "source" if expected_kind == "external" else "sink"
        raise GlyphError(
            f"{system.line}行目: system '{system.name}' の{keyword} "
            f"'{name}' は未宣言"
        )
    actual_kind = binding[0]
    if actual_kind != expected_kind:
        expected = (
            "`ext`外部入力関数"
            if expected_kind == "external"
            else "`!`外部作用関数"
        )
        keyword = "source" if expected_kind == "external" else "sink"
        raise GlyphError(
            f"{system.line}行目: system {keyword} '{name}' は"
            f"{expected}にする"
        )


def build_architecture_ir(
    source_name: str,
    program: Program,
    systems: Sequence[SystemDecl],
) -> ArchitectureIR:
    """Build a function-only call graph for every declared system boundary."""

    external_names = {
        name
        for system in systems
        for name in system.external_names
    }
    bindings = _callable_bindings(program, external_names)
    known_non_callable = _known_non_callable_names(program)
    functions = {
        name: declaration
        for name, (_kind, declaration) in bindings.items()
        if isinstance(declaration, FunctionDecl)
    }
    effect_names = {
        name
        for name, (kind, _declaration) in bindings.items()
        if kind == "effect"
    }

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

        graph = _direct_calls(
            functions,
            bindings,
            known_non_callable,
            system.name,
        )
        reachable_order = _reachable_order(graph, system.entry_name)
        reachable = set(reachable_order)

        reachable_sources = {
            name
            for name in reachable
            if bindings.get(name, ("",))[0] == "external"
        }
        reachable_sinks = {
            name
            for name in reachable
            if bindings.get(name, ("",))[0] == "effect"
        }

        if system.syntax == "legacy-flow":
            declared_sources = reachable_sources
            declared_sinks = reachable_sinks
        else:
            declared_sources = set(system.source_names)
            declared_sinks = set(system.sink_names)
            for name in system.source_names:
                _validate_role(system, name, "external", bindings)
            for name in system.sink_names:
                _validate_role(system, name, "effect", bindings)

            unreachable_sources = sorted(declared_sources - reachable_sources)
            unreachable_sinks = sorted(declared_sinks - reachable_sinks)
            missing_sources = sorted(reachable_sources - declared_sources)
            missing_sinks = sorted(reachable_sinks - declared_sinks)

            if unreachable_sources:
                raise GlyphError(
                    f"{system.line}行目: system '{system.name}' のsource "
                    f"{unreachable_sources} はentry '{system.entry_name}' "
                    "から呼び出されない"
                )
            if unreachable_sinks:
                raise GlyphError(
                    f"{system.line}行目: system '{system.name}' のsink "
                    f"{unreachable_sinks} はentry '{system.entry_name}' "
                    "から呼び出されない"
                )
            if missing_sources:
                raise GlyphError(
                    f"{system.line}行目: system '{system.name}' はentryから"
                    f"到達する外部入力 {missing_sources} をsourceとして"
                    "宣言していない"
                )
            if missing_sinks:
                raise GlyphError(
                    f"{system.line}行目: system '{system.name}' はentryから"
                    f"到達する外部作用 {missing_sinks} をsinkとして"
                    "宣言していない"
                )

        for name in reachable:
            declaration = functions.get(name)
            if declaration is not None:
                _validate_effect_exclusivity(declaration, effect_names)

        local_ids = {
            name: f"arch_{system_index}_{position}_{_safe_id(name)}"
            for position, name in enumerate(reachable_order)
        }
        components: list[ArchitectureComponent] = []
        for name in reachable_order:
            kind, declaration = bindings[name]
            role = (
                "entry"
                if name == system.entry_name
                else "source"
                if name in declared_sources
                else "sink"
                if name in declared_sinks
                else "internal"
            )
            components.append(
                ArchitectureComponent(
                    id=local_ids[name],
                    name=name,
                    kind=kind,
                    binding=name,
                    line=declaration.line,
                    role=role,
                )
            )

        evidence: list[ArchitectureEvidence] = []
        edges: list[ArchitectureEdge] = []
        for caller in reachable_order:
            if caller not in functions:
                continue
            for callee, line in graph.get(caller, ()):
                if callee not in reachable:
                    continue
                evidence_id = (
                    f"evidence_{system_index}_{len(evidence)}_call"
                )
                callee_decl = bindings[callee][1]
                evidence.append(
                    ArchitectureEvidence(
                        id=evidence_id,
                        kind="call",
                        path=(caller, callee),
                        payload_type=_canonical_type_ref(
                            callee_decl.return_type
                        ),
                        line=line,
                    )
                )
                edges.append(
                    ArchitectureEdge(
                        source_id=local_ids[caller],
                        target_id=local_ids[callee],
                        line=line,
                        kind="call",
                        payload_type=None,
                        evidence_ids=(evidence_id,),
                    )
                )

        resolved_systems.append(
            ArchitectureSystem(
                id=f"system_{system_index}_{_safe_id(system.name)}",
                name=system.name,
                entry=system.entry_name,
                ports=(),
                components=tuple(components),
                edges=tuple(edges),
                evidence=tuple(evidence),
                line=system.line,
                sources=tuple(
                    name
                    for name in reachable_order
                    if name in declared_sources
                ),
                sinks=tuple(
                    name
                    for name in reachable_order
                    if name in declared_sinks
                ),
            )
        )

    return ArchitectureIR(source_name, tuple(resolved_systems))

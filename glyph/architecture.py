from __future__ import annotations

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
    UnaryExpr,
)
from .schema import ARCHITECTURE_IR_SCHEMA, versioned_payload


@dataclass(frozen=True)
class SystemEdgeDecl:
    """Optional source assertion for one compiler-derived system edge."""

    source_name: str
    target_name: str
    line: int


@dataclass(frozen=True)
class SystemDecl:
    """A system entry point plus optional assertions about its code graph.

    Canonical syntax is `system Name=entry`. Indented `a -> b` rows are retained
    only as checked assertions: they never create nodes or edges by themselves.
    Legacy `system Name` blocks remain accepted when they contain assertions, but
    every name and edge must resolve to actual declarations and calls.
    """

    name: str
    entry_name: str | None
    edges: tuple[SystemEdgeDecl, ...]
    external_names: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class ArchitectureComponent:
    id: str
    name: str
    kind: str
    binding: str | None
    line: int


@dataclass(frozen=True)
class ArchitectureEdge:
    source_id: str
    target_id: str
    line: int


@dataclass(frozen=True)
class ArchitectureSystem:
    id: str
    name: str
    components: tuple[ArchitectureComponent, ...]
    edges: tuple[ArchitectureEdge, ...]
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


def extract_systems(source: str) -> tuple[str, tuple[SystemDecl, ...]]:
    """Extract code-derived `system` headers and mask explicit `ext` contracts.

    Canonical form:

        system DoorControl=control

    The entry must resolve after the complete Program is parsed. Optional indented
    `source -> target` rows are assertions checked against the actual call graph;
    they no longer create freehand architecture. `ext name(args):Type` is lowered
    to the existing Host boundary representation while retaining its external kind
    in every system declaration.
    """

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
        if header.count("=") > 1:
            raise GlyphError(
                f"{line}行目: systemは `system Name=entry` で宣言する"
            )
        if "=" in header:
            name, entry_name = (part.strip() for part in header.split("=", 1))
            if not entry_name.isidentifier():
                raise GlyphError(f"{line}行目: system entry名が不正: '{entry_name}'")
        else:
            name = header
            entry_name = None
        if not name.isidentifier():
            raise GlyphError(f"{line}行目: system名が不正: '{name}'")
        if name in seen_names:
            raise GlyphError(
                f"{line}行目: system '{name}' は{seen_names[name]}行目で定義済み"
            )
        seen_names[name] = line
        output[index] = ""
        assertions: list[SystemEdgeDecl] = []
        seen_edges: set[tuple[str, str]] = set()
        cursor = index + 1
        while cursor < len(lines):
            edge_original = lines[cursor]
            edge_clean = edge_original.split("#", 1)[0].rstrip()
            if not edge_clean.strip():
                output[cursor] = output[cursor]
                cursor += 1
                continue
            if not edge_clean[:1].isspace():
                break
            edge_line = cursor + 1
            edge_text = edge_clean.strip()
            if edge_text.count("->") != 1:
                raise GlyphError(
                    f"{edge_line}行目: system assertionは `source -> target` の形式にする"
                )
            source_name, target_name = (
                part.strip() for part in edge_text.split("->", 1)
            )
            if not source_name.isidentifier() or not target_name.isidentifier():
                raise GlyphError(
                    f"{edge_line}行目: system node名は識別子にする: {edge_text}"
                )
            if source_name == target_name:
                raise GlyphError(
                    f"{edge_line}行目: self-edge assertion '{edge_text}' は書けない"
                )
            pair = (source_name, target_name)
            if pair in seen_edges:
                raise GlyphError(
                    f"{edge_line}行目: system assertion '{edge_text}' が重複"
                )
            seen_edges.add(pair)
            assertions.append(SystemEdgeDecl(source_name, target_name, edge_line))
            output[cursor] = ""
            cursor += 1
        if entry_name is None and not assertions:
            raise GlyphError(
                f"{line}行目: system '{name}' は `system {name}=entry` として"
                "実装済み関数へ結び付ける"
            )
        systems.append(
            SystemDecl(name, entry_name, tuple(assertions), external_names, line)
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
                "宣言されていない。外部境界なら `ext name(args):Type` で宣言する"
            )
        output.append((callee, line))
    return tuple(output)


def _derived_edges(
    entry_name: str,
    bindings: dict[str, tuple[str, FunctionDecl | ExternDecl]],
    known_non_callable: set[str],
    system: SystemDecl,
) -> tuple[list[str], dict[tuple[str, str], int]]:
    entry = bindings.get(entry_name)
    if entry is None:
        raise GlyphError(
            f"{system.line}行目: system '{system.name}' のentry '{entry_name}' は未宣言"
        )
    if entry[0] != "function":
        raise GlyphError(
            f"{system.line}行目: system entry '{entry_name}' は本体を持つ `>` 関数にする"
        )

    functions = {
        name: declaration
        for name, (_, declaration) in bindings.items()
        if isinstance(declaration, FunctionDecl)
    }
    ordered = [entry_name]
    queued = {entry_name}
    cursor = 0
    edges: dict[tuple[str, str], int] = {}
    while cursor < len(ordered):
        source = ordered[cursor]
        cursor += 1
        declaration = functions.get(source)
        if declaration is None:
            continue
        for target, line in _visible_calls(
            declaration,
            functions,
            bindings,
            known_non_callable,
            system_name=system.name,
            expanding=(source,),
        ):
            edges.setdefault((source, target), line)
            if target not in queued:
                queued.add(target)
                ordered.append(target)
    return ordered, edges


def _validate_assertion_nodes(
    system: SystemDecl,
    bindings: dict[str, tuple[str, FunctionDecl | ExternDecl]],
) -> None:
    for assertion in system.edges:
        for name in (assertion.source_name, assertion.target_name):
            if name not in bindings:
                raise GlyphError(
                    f"{assertion.line}行目: system '{system.name}' node '{name}' は未宣言。"
                    "外部境界なら `ext name(args):Type` で宣言する"
                )


def build_architecture_ir(
    source_name: str, program: Program, systems: Sequence[SystemDecl]
) -> ArchitectureIR:
    external_names = {
        name for system in systems for name in system.external_names
    }
    bindings = _callable_bindings(program, external_names)
    known_non_callable = _known_non_callable_names(program)
    functions = {
        name: declaration
        for name, (_, declaration) in bindings.items()
        if isinstance(declaration, FunctionDecl)
    }

    resolved_systems: list[ArchitectureSystem] = []
    for system_index, system in enumerate(systems):
        _validate_assertion_nodes(system, bindings)

        if system.entry_name is not None:
            ordered_names, edge_lines = _derived_edges(
                system.entry_name, bindings, known_non_callable, system
            )
            for assertion in system.edges:
                pair = (assertion.source_name, assertion.target_name)
                if pair not in edge_lines:
                    raise GlyphError(
                        f"{assertion.line}行目: system assertion "
                        f"'{assertion.source_name} -> {assertion.target_name}' は"
                        "entryから導出したコード上の直接呼出しに存在しない"
                    )
        else:
            ordered_names = []
            edge_lines = {}
            for assertion in system.edges:
                if assertion.source_name not in ordered_names:
                    ordered_names.append(assertion.source_name)
                if assertion.target_name not in ordered_names:
                    ordered_names.append(assertion.target_name)
                source_decl = functions.get(assertion.source_name)
                if source_decl is None:
                    raise GlyphError(
                        f"{assertion.line}行目: system assertionのsource "
                        f"'{assertion.source_name}' は本体を持つ `>` 関数ではない"
                    )
                actual = {
                    target
                    for target, _ in _visible_calls(
                        source_decl,
                        functions,
                        bindings,
                        known_non_callable,
                        system_name=system.name,
                        expanding=(assertion.source_name,),
                    )
                }
                if assertion.target_name not in actual:
                    raise GlyphError(
                        f"{assertion.line}行目: system assertion "
                        f"'{assertion.source_name} -> {assertion.target_name}' は"
                        "コード上の直接呼出しではない"
                    )
                edge_lines[(assertion.source_name, assertion.target_name)] = assertion.line

        local_ids: dict[str, str] = {}
        components: list[ArchitectureComponent] = []
        for component_index, name in enumerate(ordered_names):
            kind, declaration = bindings[name]
            local_id = f"arch_{system_index}_{component_index}_{_safe_id(name)}"
            local_ids[name] = local_id
            components.append(
                ArchitectureComponent(
                    local_id,
                    name,
                    kind,
                    name,
                    declaration.line,
                )
            )

        edges = tuple(
            ArchitectureEdge(local_ids[source], local_ids[target], line)
            for (source, target), line in edge_lines.items()
        )
        resolved_systems.append(
            ArchitectureSystem(
                f"system_{system_index}_{_safe_id(system.name)}",
                system.name,
                tuple(components),
                edges,
                system.line,
            )
        )

    return ArchitectureIR(source_name, tuple(resolved_systems))

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

from .compiler import (
    AliasDecl,
    ExternDecl,
    FunctionDecl,
    GlyphError,
    ProductDecl,
    Program,
    SumDecl,
)
from .schema import ARCHITECTURE_IR_SCHEMA, versioned_payload


@dataclass(frozen=True)
class SystemEdgeDecl:
    source_name: str
    target_name: str
    line: int


@dataclass(frozen=True)
class SystemDecl:
    name: str
    edges: tuple[SystemEdgeDecl, ...]
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


def extract_systems(source: str) -> tuple[str, tuple[SystemDecl, ...]]:
    """Extract `system Name` blocks and preserve all source line numbers."""

    lines = source.splitlines()
    output = list(lines)
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
        name = stripped[len("system ") :].strip()
        if not name.isidentifier():
            raise GlyphError(f"{line}行目: system名が不正: '{name}'")
        if name in seen_names:
            raise GlyphError(
                f"{line}行目: system '{name}' は{seen_names[name]}行目で定義済み"
            )
        seen_names[name] = line
        output[index] = ""
        edges: list[SystemEdgeDecl] = []
        seen_edges: set[tuple[str, str]] = set()
        cursor = index + 1
        while cursor < len(lines):
            edge_original = lines[cursor]
            edge_clean = edge_original.split("#", 1)[0].rstrip()
            if not edge_clean.strip():
                output[cursor] = edge_original
                cursor += 1
                continue
            if not edge_clean[:1].isspace():
                break
            edge_line = cursor + 1
            edge_text = edge_clean.strip()
            if edge_text.count("->") != 1:
                raise GlyphError(
                    f"{edge_line}行目: system接続は `source -> target` の1本だけを書く"
                )
            source_name, target_name = (
                part.strip() for part in edge_text.split("->", 1)
            )
            if not source_name.isidentifier() or not target_name.isidentifier():
                raise GlyphError(
                    f"{edge_line}行目: component名は識別子にする: {edge_text}"
                )
            if source_name == target_name:
                raise GlyphError(
                    f"{edge_line}行目: self-edge '{source_name} -> {target_name}' は書けない"
                )
            pair = (source_name, target_name)
            if pair in seen_edges:
                raise GlyphError(
                    f"{edge_line}行目: 接続 '{source_name} -> {target_name}' が重複"
                )
            seen_edges.add(pair)
            edges.append(SystemEdgeDecl(source_name, target_name, edge_line))
            output[cursor] = ""
            cursor += 1
        if not edges:
            raise GlyphError(f"{line}行目: system '{name}' に接続がない")
        systems.append(SystemDecl(name, tuple(edges), line))
        index = cursor

    return (
        "\n".join(output) + ("\n" if source.endswith("\n") else ""),
        tuple(systems),
    )


def build_architecture_ir(
    source_name: str, program: Program, systems: Sequence[SystemDecl]
) -> ArchitectureIR:
    bindings: dict[str, list[tuple[str, str]]] = {}
    for declaration in program.declarations:
        if isinstance(declaration, FunctionDecl):
            bindings.setdefault(declaration.name, []).append(("function", declaration.name))
        elif isinstance(declaration, ExternDecl):
            bindings.setdefault(declaration.name, []).append(("effect", declaration.name))
        elif isinstance(declaration, (ProductDecl, SumDecl, AliasDecl)):
            bindings.setdefault(declaration.name, []).append(("data", declaration.name))

    resolved_systems: list[ArchitectureSystem] = []
    for system_index, system in enumerate(systems):
        component_lines: dict[str, int] = {}
        ordered_names: list[str] = []
        for edge in system.edges:
            for name in (edge.source_name, edge.target_name):
                if name not in component_lines:
                    component_lines[name] = edge.line
                    ordered_names.append(name)

        components: list[ArchitectureComponent] = []
        local_ids: dict[str, str] = {}
        for component_index, name in enumerate(ordered_names):
            candidates = bindings.get(name, [])
            if len(candidates) > 1:
                kinds = ", ".join(kind for kind, _ in candidates)
                raise GlyphError(
                    f"{component_lines[name]}行目: component '{name}' のbindingが曖昧: {kinds}"
                )
            if candidates:
                kind, binding = candidates[0]
            else:
                kind, binding = "external", None
            local_id = f"arch_{system_index}_{component_index}_{_safe_id(name)}"
            local_ids[name] = local_id
            components.append(
                ArchitectureComponent(
                    local_id,
                    name,
                    kind,
                    binding,
                    component_lines[name],
                )
            )

        edges = tuple(
            ArchitectureEdge(
                local_ids[edge.source_name], local_ids[edge.target_name], edge.line
            )
            for edge in system.edges
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

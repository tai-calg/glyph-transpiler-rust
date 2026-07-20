from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from .architecture import ArchitectureIR, ArchitectureSystem
from .compiler import (
    CallExpr,
    ExternDecl,
    Expr,
    GlyphError,
    NameExpr,
    Param,
    Program,
    TypeRef,
    _parse_named_signature,
)
from .functional import FunctionalPatternRustGenerator
from .semantic import SemanticModel


@dataclass(frozen=True)
class OpaqueSeed:
    line: int
    note: str


@dataclass(frozen=True)
class OpaqueDecl:
    """A pure function contract implemented manually in Rust.

    Surface syntax:

        ~route(graph:Graph,start:Node,goal:Node):Path # TODO: A*

    `~` means that Glyph knows the typed contract and call graph position but
    deliberately does not contain the algorithm body.
    """

    name: str
    params: tuple[Param, ...]
    return_type: TypeRef
    line: int
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "params": [
                {"name": param.name, "type": _render_type(param.ty)}
                for param in self.params
            ],
            "return_type": _render_type(self.return_type),
            "line": self.line,
            "note": self.note,
            "implementation": "manual.rs",
        }


def _render_type(ty: TypeRef) -> str:
    if not ty.args:
        return ty.name
    return f"{ty.name}<{','.join(_render_type(arg) for arg in ty.args)}>"


def _split_comment(line: str) -> tuple[str, str]:
    marker = line.find("#")
    if marker < 0:
        return line.rstrip(), ""
    return line[:marker].rstrip(), line[marker + 1 :].strip()


def _replace_marker(line: str, marker: str) -> str:
    code, note = _split_comment(line)
    position = len(code) - len(code.lstrip())
    if position >= len(code):
        return line
    replaced = code[:position] + marker + code[position + 1 :]
    return replaced + ((" # " + note) if note else "")


def mask_opaque_as_effect(source: str) -> tuple[str, tuple[OpaqueSeed, ...]]:
    """Temporarily map `~` to `!` so compact type syntax can be expanded."""

    lines = source.splitlines()
    output = list(lines)
    seeds: list[OpaqueSeed] = []
    for index, original in enumerate(lines):
        code, note = _split_comment(original)
        stripped = code.strip()
        if not stripped or code[:1].isspace() or not stripped.startswith("~"):
            continue
        line = index + 1
        if stripped == "~":
            raise GlyphError(f"{line}行目: ~name(args):Type の形式が必要")
        seeds.append(OpaqueSeed(line, note))
        output[index] = _replace_marker(original, "!")
    return (
        "\n".join(output) + ("\n" if source.endswith("\n") else ""),
        tuple(seeds),
    )


def expose_opaque_as_pure(
    source: str, seeds: Sequence[OpaqueSeed]
) -> tuple[str, tuple[OpaqueDecl, ...]]:
    """Map masked declarations to bodyless pure signatures for pipeline analysis."""

    if not seeds:
        return source, ()
    lines = source.splitlines()
    declarations: list[OpaqueDecl] = []
    seen: dict[str, int] = {}
    for seed in seeds:
        if not 1 <= seed.line <= len(lines):
            raise GlyphError(f"{seed.line}行目: ~宣言の位置を復元できない")
        lines[seed.line - 1] = _replace_marker(lines[seed.line - 1], ">")
        code, _ = _split_comment(lines[seed.line - 1])
        stripped = code.strip()
        name, params, return_type, body = _parse_named_signature(
            stripped[1:].strip(), seed.line
        )
        if body is not None:
            raise GlyphError(
                f"{seed.line}行目: ~関数はGlyph本体を書かずRust側で実装する"
            )
        if name in seen:
            raise GlyphError(
                f"{seed.line}行目: ~関数 '{name}' は{seen[name]}行目で定義済み"
            )
        seen[name] = seed.line
        declarations.append(
            OpaqueDecl(name, params, return_type, seed.line, seed.note)
        )
    return (
        "\n".join(lines) + ("\n" if source.endswith("\n") else ""),
        tuple(declarations),
    )


def lower_opaque_to_extern(source: str, seeds: Sequence[OpaqueSeed]) -> str:
    """Map pure signatures to parser-compatible extern declarations."""

    if not seeds:
        return source
    lines = source.splitlines()
    for seed in seeds:
        if 1 <= seed.line <= len(lines):
            lines[seed.line - 1] = _replace_marker(lines[seed.line - 1], "!")
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")


def without_opaque_externs(program: Program, opaques: Sequence[OpaqueDecl]) -> Program:
    """Validation view where `~` calls are unknown pure calls, not effects."""

    names = {item.name for item in opaques}
    return Program(
        tuple(
            declaration
            for declaration in program.declarations
            if not (
                isinstance(declaration, ExternDecl)
                and declaration.name in names
            )
        )
    )


class OpaqueAwareRustGenerator(FunctionalPatternRustGenerator):
    """Generate `~foo(...)` calls as stable `crate::manual::foo(...)` calls."""

    def __init__(self, program: Program, opaques: Sequence[OpaqueDecl]):
        self.opaque_names = {item.name for item in opaques}
        filtered = without_opaque_externs(program, opaques)
        super().__init__(filtered)

    def _expr(self, expr: Expr, parent_prec: int = 0) -> str:
        if isinstance(expr, NameExpr) and expr.name in self.opaque_names:
            return f"crate::manual::{expr.name}"
        if (
            isinstance(expr, CallExpr)
            and isinstance(expr.callee, NameExpr)
            and expr.callee.name in self.opaque_names
        ):
            arguments = ", ".join(self._expr(arg) for arg in expr.args)
            return f"crate::manual::{expr.callee.name}({arguments})"
        return super()._expr(expr, parent_prec)


def generate_manual_scaffold(
    program: Program, opaques: Sequence[OpaqueDecl]
) -> str:
    if not opaques:
        return ""
    generator = FunctionalPatternRustGenerator(program)
    lines = [
        "// Created once by Glyph Studio.",
        "// This file is intentionally not overwritten after creation.",
        "// Implement the pure `~` contracts below in Rust.",
        "use crate::generated::*;",
        "",
    ]
    for declaration in opaques:
        signature = generator._signature_tail(
            declaration.params, declaration.return_type
        )
        note = declaration.note or "implement the complex algorithm in Rust"
        message = (
            f"Glyph ~{declaration.name}: {note}"
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", " ")
        )
        lines.extend(
            [
                "#[allow(unused_variables)]",
                f"pub fn {declaration.name}{signature} {{",
                f'    todo!("{message}")',
                "}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def relabel_semantic_model(
    semantic: SemanticModel, opaques: Sequence[OpaqueDecl]
) -> SemanticModel:
    names = {item.name for item in opaques}
    if not names:
        return semantic
    symbols = tuple(
        replace(record, kind="rust")
        if record.name in names and record.kind == "effect"
        else record
        for record in semantic.symbols
    )
    return replace(semantic, symbols=symbols)


def relabel_architecture(
    architecture: ArchitectureIR, opaques: Sequence[OpaqueDecl]
) -> ArchitectureIR:
    names = {item.name for item in opaques}
    if not names:
        return architecture
    systems: list[ArchitectureSystem] = []
    for system in architecture.systems:
        components = tuple(
            replace(component, kind="rust")
            if component.name in names and component.kind == "effect"
            else component
            for component in system.components
        )
        systems.append(replace(system, components=components))
    return replace(architecture, systems=tuple(systems))

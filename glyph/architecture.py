"""Compatibility facade for the canonical System architecture implementation.

The core parser temporarily lowers both ``~`` pure Rust contracts and ``!``
external effects to ``ExternDecl``. System architecture must retain the source
kind distinction: ``~`` is an internal callable, while only ``!`` may be a
``sink``. This facade carries opaque identity through the lowering pipeline and
builds the architecture against an architecture-only pure-function view.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from .compiler import ExternDecl, FunctionDecl, Program
from .system_architecture import (
    ArchitectureComponent,
    ArchitectureEdge,
    ArchitectureEvidence,
    ArchitectureIR,
    ArchitecturePort,
    ArchitectureSystem,
    SystemDecl,
    SystemEdgeDecl,
    SystemPortDecl,
    build_architecture_ir as _build_architecture_ir,
    extract_systems as _extract_systems,
)


_OPAQUE_NAME_PREFIX = "__glyph_opaque_pure__:"
_OPAQUE_MASK_MARKER = "__glyph_opaque_pure__"


def _top_level_opaque_names(source: str) -> tuple[str, ...]:
    names: list[str] = []
    for original in source.splitlines():
        code, marker, comment = original.partition("#")
        code = code.rstrip()
        stripped = code.strip()
        if not stripped or code[:1].isspace():
            continue

        if stripped.startswith("~"):
            signature = stripped[1:].strip()
        elif (
            stripped.startswith("!")
            and marker
            and _OPAQUE_MASK_MARKER in comment
        ):
            signature = stripped[1:].strip()
        else:
            continue

        open_pos = signature.find("(")
        if open_pos <= 0:
            continue
        name = signature[:open_pos].strip()
        if name.isidentifier() and name not in names:
            names.append(name)
    return tuple(names)


def extract_systems(source: str) -> tuple[str, tuple[SystemDecl, ...]]:
    """Extract Systems while retaining source-only ``~`` function identity.

    ``SystemDecl`` predates explicit opaque-function metadata. A private marker
    in ``external_names`` is used only to survive the generic dataclass line
    remapper. It is removed temporarily before the canonical architecture
    builder classifies real ``ext`` declarations.
    """

    cleaned, systems = _extract_systems(source)
    opaque_names = _top_level_opaque_names(source)
    if not opaque_names:
        return cleaned, systems

    markers = tuple(f"{_OPAQUE_NAME_PREFIX}{name}" for name in opaque_names)
    for system in systems:
        system.external_names = (*system.external_names, *markers)
    return cleaned, systems


def _opaque_names(systems: Sequence[SystemDecl]) -> set[str]:
    return {
        name[len(_OPAQUE_NAME_PREFIX) :]
        for system in systems
        for name in system.external_names
        if name.startswith(_OPAQUE_NAME_PREFIX)
    }


def _real_external_names(system: SystemDecl) -> tuple[str, ...]:
    return tuple(
        name
        for name in system.external_names
        if not name.startswith(_OPAQUE_NAME_PREFIX)
    )


def _architecture_program(program: Program, opaque_names: set[str]) -> Program:
    """Represent bodyless ``~`` contracts as pure leaf callables for this IR."""

    if not opaque_names:
        return program
    declarations = []
    for declaration in program.declarations:
        if isinstance(declaration, ExternDecl) and declaration.name in opaque_names:
            declarations.append(
                FunctionDecl(
                    name=declaration.name,
                    params=declaration.params,
                    return_type=declaration.return_type,
                    expression=None,
                    guards=(),
                    line=declaration.line,
                )
            )
        else:
            declarations.append(declaration)
    return Program(tuple(declarations))


def build_architecture_ir(
    source_name: str,
    program: Program,
    systems: Sequence[SystemDecl],
) -> ArchitectureIR:
    """Build function-only System IR without treating ``~`` as an Effect."""

    opaque_names = _opaque_names(systems)
    saved_external_names = [system.external_names for system in systems]
    for system in systems:
        system.external_names = _real_external_names(system)
    try:
        architecture = _build_architecture_ir(
            source_name,
            _architecture_program(program, opaque_names),
            systems,
        )
    finally:
        for system, names in zip(systems, saved_external_names, strict=True):
            system.external_names = names

    if not opaque_names:
        return architecture

    projected_systems: list[ArchitectureSystem] = []
    for system in architecture.systems:
        components = tuple(
            replace(component, kind="rust")
            if component.name in opaque_names and component.kind == "function"
            else component
            for component in system.components
        )
        projected_systems.append(replace(system, components=components))
    return replace(architecture, systems=tuple(projected_systems))


__all__ = [
    "ArchitectureComponent",
    "ArchitectureEdge",
    "ArchitectureEvidence",
    "ArchitectureIR",
    "ArchitecturePort",
    "ArchitectureSystem",
    "SystemDecl",
    "SystemEdgeDecl",
    "SystemPortDecl",
    "build_architecture_ir",
    "extract_systems",
]

"""Compatibility export for the canonical System architecture implementation."""

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
    build_architecture_ir,
    extract_systems,
)

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

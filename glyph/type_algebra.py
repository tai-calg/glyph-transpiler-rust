from __future__ import annotations

from dataclasses import asdict
from typing import Sequence

from .compiler import Program
from .machine_coverage import (
    CoverageBinding,
    MachineCoverage,
    MachineCoverageCase,
    MachineGuardCoverage,
    build_machine_coverage,
)
from .machine_coverage_diagnostics import (
    MachineCoverageDiagnostic,
    build_machine_coverage_diagnostics,
)
from .type_algebra_impl import (
    AlgebraMonomial,
    ConversionFunction,
    ExhaustiveCase,
    IsomorphismClass,
    TypeAlgebraIR as CoreTypeAlgebraIR,
    TypeAlgebraSourceRef,
    TypeAlgebraType,
    build_type_algebra_ir as _build_core_type_algebra_ir,
    render_type_algebra_rust as _render_core_type_algebra_rust,
)
from .type_algebra_tooling import (
    StructuralConversion,
    TypeAlgebraDiagnostic,
    build_structural_conversions,
    build_type_algebra_diagnostics,
    render_structural_conversion_rust,
    tooling_payload as _tooling_payload,
)


class TypeAlgebraIR:
    """Backward-compatible Type Algebra IR enriched with user-facing tooling data."""

    def __init__(
        self,
        core: CoreTypeAlgebraIR,
        diagnostics: tuple[TypeAlgebraDiagnostic, ...],
        structural_conversions: tuple[StructuralConversion, ...],
    ) -> None:
        self.core = core
        self.source_name = core.source_name
        self.exhaustive_limit = core.exhaustive_limit
        self.types = core.types
        self.isomorphism_classes = core.isomorphism_classes
        self.conversions = core.conversions
        self.diagnostics = diagnostics
        self.structural_conversions = structural_conversions

    def to_dict(self) -> dict[str, object]:
        payload = self.core.to_dict()
        payload["diagnostics"] = [asdict(item) for item in self.diagnostics]
        payload["structural_conversions"] = [
            asdict(item) for item in self.structural_conversions
        ]
        return payload


def build_type_algebra_ir(
    source_name: str,
    program: Program,
    *,
    exhaustive_limit: int = 64,
) -> TypeAlgebraIR:
    core = _build_core_type_algebra_ir(
        source_name,
        program,
        exhaustive_limit=exhaustive_limit,
    )
    return TypeAlgebraIR(
        core,
        build_type_algebra_diagnostics(program, core),
        build_structural_conversions(program),
    )


def render_type_algebra_rust(ir: TypeAlgebraIR | CoreTypeAlgebraIR) -> str:
    core = ir.core if isinstance(ir, TypeAlgebraIR) else ir
    rendered = _render_core_type_algebra_rust(core)
    structural = (
        render_structural_conversion_rust(ir.structural_conversions)
        if isinstance(ir, TypeAlgebraIR)
        else ""
    )
    return rendered.rstrip() + "\n" + structural


def tooling_payload(
    diagnostics: Sequence[TypeAlgebraDiagnostic | MachineCoverageDiagnostic],
    structural: Sequence[StructuralConversion],
    machine_coverage: Sequence[MachineCoverage] = (),
) -> dict[str, object]:
    combined = (
        *diagnostics,
        *build_machine_coverage_diagnostics(machine_coverage),
    )
    return _tooling_payload(combined, structural, machine_coverage)


__all__ = [
    "AlgebraMonomial",
    "ConversionFunction",
    "CoverageBinding",
    "ExhaustiveCase",
    "IsomorphismClass",
    "MachineCoverage",
    "MachineCoverageCase",
    "MachineCoverageDiagnostic",
    "MachineGuardCoverage",
    "StructuralConversion",
    "TypeAlgebraDiagnostic",
    "TypeAlgebraIR",
    "TypeAlgebraSourceRef",
    "TypeAlgebraType",
    "build_machine_coverage",
    "build_machine_coverage_diagnostics",
    "build_structural_conversions",
    "build_type_algebra_diagnostics",
    "build_type_algebra_ir",
    "render_type_algebra_rust",
    "tooling_payload",
]

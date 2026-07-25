from __future__ import annotations

from dataclasses import asdict, replace
from typing import Sequence

from .compiler import Program
from .machine_coverage import (
    CoverageBinding,
    MachineCoverage,
    MachineCoverageCase,
    MachineGuardCoverage,
)
from .machine_coverage_partitioned import (
    build_machine_coverage as _build_machine_coverage_v2,
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


Diagnostic = TypeAlgebraDiagnostic | MachineCoverageDiagnostic


class TypeAlgebraIR:
    """Backward-compatible Type Algebra IR enriched with user-facing tooling data."""

    def __init__(
        self,
        core: CoreTypeAlgebraIR,
        diagnostics: tuple[Diagnostic, ...],
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


def _diagnostic_key(item: Diagnostic) -> tuple[object, ...]:
    return (item.code, item.severity, item.message, item.subject, item.line)


def _unique_diagnostics(items: Sequence[Diagnostic]) -> tuple[Diagnostic, ...]:
    unique: dict[tuple[object, ...], Diagnostic] = {}
    for item in items:
        unique.setdefault(_diagnostic_key(item), item)
    return tuple(unique.values())


def build_machine_coverage(*args, **kwargs) -> tuple[MachineCoverage, ...]:
    """Run coverage v2 and attach its warnings to the transient analysis model."""

    rows = _build_machine_coverage_v2(*args, **kwargs)
    fixed: list[MachineCoverage] = []
    for coverage in rows:
        guards = tuple(
            replace(
                guard,
                true_cases=guard.first_match_cases,
                shadowed_cases=0,
                unreachable=False,
                classification="reachable",
            )
            if guard.condition == "always"
            else guard
            for guard in coverage.guards
        )
        fixed.append(replace(coverage, guards=guards))
    result = tuple(fixed)

    algebra = kwargs.get("algebra")
    if algebra is None and len(args) >= 4:
        algebra = args[3]
    if isinstance(algebra, TypeAlgebraIR):
        algebra.diagnostics = _unique_diagnostics(
            (*algebra.diagnostics, *build_machine_coverage_diagnostics(result))
        )
    return result


def _add_exact_coverage_counts(
    payload: dict[str, object],
    machine_coverage: Sequence[MachineCoverage],
) -> dict[str, object]:
    rows = payload.get("machine_coverage")
    if not isinstance(rows, list):
        return payload
    for coverage, row in zip(machine_coverage, rows):
        if not isinstance(row, dict):
            continue
        row.update(
            {
                "defined_pairs_exact": str(coverage.defined_pairs),
                "rejected_pairs_exact": str(coverage.rejected_pairs),
                "fallthrough_pairs_exact": str(coverage.fallthrough_pairs),
                "missing_pairs_exact": (
                    None
                    if coverage.missing_pairs is None
                    else str(coverage.missing_pairs)
                ),
                "overlap_pairs_exact": str(coverage.overlap_pairs),
                "unknown_pairs_exact": str(coverage.unknown_pairs),
            }
        )
        guard_rows = row.get("guards")
        if not isinstance(guard_rows, list):
            continue
        for guard, guard_row in zip(coverage.guards, guard_rows):
            if not isinstance(guard_row, dict):
                continue
            guard_row.update(
                {
                    "true_cases_exact": str(guard.true_cases),
                    "first_match_cases_exact": str(guard.first_match_cases),
                    "shadowed_cases_exact": str(guard.shadowed_cases),
                    "unknown_cases_exact": str(guard.unknown_cases),
                }
            )
    return payload


def tooling_payload(
    diagnostics: Sequence[Diagnostic],
    structural: Sequence[StructuralConversion],
    machine_coverage: Sequence[MachineCoverage] = (),
) -> dict[str, object]:
    combined = _unique_diagnostics(
        (*diagnostics, *build_machine_coverage_diagnostics(machine_coverage))
    )
    payload = _tooling_payload(combined, structural, machine_coverage)
    return _add_exact_coverage_counts(payload, machine_coverage)


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

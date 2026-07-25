from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .machine_coverage import MachineCoverage


@dataclass(frozen=True)
class MachineCoverageDiagnostic:
    code: str
    severity: str
    message: str
    subject: str
    line: int


def _case_inputs(case: object) -> str:
    regions = getattr(case, "regions", ())
    bindings = regions or getattr(case, "inputs", ())
    rendered = ", ".join(f"{item.name}={item.value}" for item in bindings)
    multiplicity = str(getattr(case, "multiplicity", "1"))
    return rendered + (f" ×{multiplicity}" if multiplicity != "1" else "")


def _witnesses(coverage: MachineCoverage, outcome: str, limit: int = 3) -> str:
    selected = [case for case in coverage.cases if case.outcome == outcome][:limit]
    if not selected:
        return ""
    rendered = []
    for case in selected:
        inputs = _case_inputs(case)
        rendered.append(case.selector + (f"; {inputs}" if inputs else ""))
    return " 例: " + " | ".join(rendered)


def _overlap_witnesses(coverage: MachineCoverage, limit: int = 3) -> str:
    selected = [case for case in coverage.cases if len(case.matching_clauses) > 1][:limit]
    if not selected:
        return ""
    rendered = []
    for case in selected:
        inputs = _case_inputs(case)
        clauses = ",".join(map(str, case.matching_clauses))
        rendered.append(
            case.selector
            + (f"; {inputs}" if inputs else "")
            + f" clauses={clauses}"
        )
    return " 例: " + " | ".join(rendered)


def build_machine_coverage_diagnostics(
    coverages: Sequence[MachineCoverage],
) -> tuple[MachineCoverageDiagnostic, ...]:
    diagnostics: list[MachineCoverageDiagnostic] = []
    for coverage in coverages:
        line = next(
            (
                guard.line
                for guard in coverage.guards
                if guard.line > 0
            ),
            1,
        )
        if coverage.missing_pairs not in {None, "0"}:
            diagnostics.append(
                MachineCoverageDiagnostic(
                    code="machine-coverage-missing",
                    severity="warning",
                    message=(
                        f"machine `{coverage.machine}` に未定義のselector×inputケースが"
                        f" {coverage.missing_pairs}件ある"
                        + _witnesses(coverage, "missing")
                    ),
                    subject=coverage.machine,
                    line=line,
                )
            )
        if coverage.overlap_pairs:
            diagnostics.append(
                MachineCoverageDiagnostic(
                    code="machine-coverage-overlap",
                    severity="warning",
                    message=(
                        f"machine `{coverage.machine}` で複数ガードが同時成立するケースが"
                        f" {coverage.overlap_pairs}件あり、結果が記述順に依存する"
                        + _overlap_witnesses(coverage)
                    ),
                    subject=coverage.machine,
                    line=line,
                )
            )
        unreachable = [guard for guard in coverage.guards if guard.unreachable]
        for guard in unreachable:
            diagnostics.append(
                MachineCoverageDiagnostic(
                    code="machine-coverage-unreachable",
                    severity="warning",
                    message=(
                        f"machine `{coverage.machine}` のガード#{guard.index}は"
                        f" {guard.classification} で到達不能: {guard.condition}"
                    ),
                    subject=coverage.machine,
                    line=guard.line,
                )
            )
        if coverage.unknown_pairs:
            diagnostics.append(
                MachineCoverageDiagnostic(
                    code="machine-coverage-unknown",
                    severity="warning",
                    message=(
                        f"machine `{coverage.machine}` は判定不能なケースを"
                        f" {coverage.unknown_pairs}件含む。未定義とは区別している"
                        + _witnesses(coverage, "unknown")
                    ),
                    subject=coverage.machine,
                    line=line,
                )
            )
        elif not coverage.exact and coverage.reason:
            diagnostics.append(
                MachineCoverageDiagnostic(
                    code="machine-coverage-unknown",
                    severity="warning",
                    message=(
                        f"machine `{coverage.machine}` の網羅性を確定できない: "
                        f"{coverage.reason}"
                    ),
                    subject=coverage.machine,
                    line=line,
                )
            )
    return tuple(diagnostics)

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from .compiler import AliasDecl, BoolExpr, CallExpr, NameExpr, NumberExpr, Program, TypeRef
from .machine import MachineDecl
from .machine_coverage import (
    MachineCoverage,
    MachineCoverageCase,
    _FiniteDomain,
    _machine_parts,
)


_DEFAULT_WITNESS_LIMIT = 256
_RESULT_NAMES = {"R", "Result"}


@dataclass(frozen=True)
class MachineWitnessCaseReport:
    case_index: int
    test_name: str | None
    generated: bool
    reason: str | None


@dataclass(frozen=True)
class MachineWitnessReport:
    machine: str
    generated_tests: int
    skipped_cases: int
    complete: bool
    reason: str | None
    cases: tuple[MachineWitnessCaseReport, ...]


def _snake(name: str) -> str:
    out: list[str] = []
    for index, ch in enumerate(name):
        if ch.isupper() and index and not name[index - 1].isupper():
            out.append("_")
        out.append(ch.lower() if ch.isalnum() else "_")
    return "".join(out).strip("_") or "machine"


def _resolve_alias(program: Program, ty: TypeRef) -> TypeRef:
    aliases = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, AliasDecl)
    }
    seen: set[str] = set()
    current = ty
    while not current.args and current.name in aliases and current.name not in seen:
        seen.add(current.name)
        current = aliases[current.name].target
    return current


def _argument_rust(
    argument: object,
    machine: MachineDecl,
    state_rust: str,
    input_values: Mapping[str, str],
) -> str | None:
    if isinstance(argument, NameExpr):
        if argument.name == machine.state_param.name:
            return state_rust
        return input_values.get(argument.name)
    if isinstance(argument, BoolExpr):
        return "true" if argument.value else "false"
    if isinstance(argument, NumberExpr):
        return argument.value
    return None


def _state_witness(
    domain: _FiniteDomain,
    state_type: str,
    selector_field: str,
    selector_display: str,
) -> str | None:
    states = domain.values_for_name(state_type)
    if states is None:
        return None
    for state in states:
        selector = state.field(selector_field)
        if selector is not None and selector.display == selector_display:
            return state.display
    return None


def _case_test(
    program: Program,
    machine: MachineDecl,
    coverage: MachineCoverage,
    case: MachineCoverageCase,
    domain: _FiniteDomain,
) -> tuple[str | None, str | None, str | None]:
    parts = _machine_parts(program, machine)
    if parts is None:
        return None, None, "selector or next function could not be resolved"
    state_decl, _, selector_field, selector_sum, next_decl = parts
    if case.outcome in {"missing", "unknown"}:
        return None, None, f"{case.outcome} cases do not have a deterministic executable branch"
    if case.selected_clause is None:
        return None, None, "no selected clause"

    state_rust = _state_witness(
        domain,
        state_decl.name,
        selector_field,
        case.selector,
    )
    if state_rust is None:
        return (
            None,
            None,
            "the complete state value cannot be constructed within the witness limit",
        )

    next_call = machine.next_expr
    if not isinstance(next_call, CallExpr):
        return None, None, "machine next expression is not a direct call"
    input_values = {binding.name: binding.value for binding in case.inputs}
    arguments: list[str] = []
    for argument in next_call.args:
        rendered = _argument_rust(argument, machine, state_rust, input_values)
        if rendered is None:
            return (
                None,
                None,
                "next-call arguments are not direct state/input values or literals",
            )
        arguments.append(rendered)
    call = f"{next_decl.name}({', '.join(arguments)})"

    return_type = _resolve_alias(program, next_decl.return_type)
    is_result = return_type.name in _RESULT_NAMES and len(return_type.args) == 2
    returns_state = (
        is_result and _resolve_alias(program, return_type.args[0]).name == state_decl.name
    ) or (not is_result and return_type.name == state_decl.name)
    if not returns_state:
        return None, None, "next function does not return the state type or Result<State, E>"

    test_name = f"witness_{_snake(machine.name)}_case_{case.index:03d}"
    if case.outcome == "rejected":
        if not is_result:
            return None, None, "rejected outcome requires Result<State, E>"
        assertion = f"assert!(matches!({call}, Err(_)));"
    else:
        target = case.target_state
        variant = next(
            (item for item in selector_sum.variants if item.name == target),
            None,
        )
        if target is None or variant is None:
            return None, None, "target selector variant is not structurally known"
        if variant.tuple_types or variant.fields:
            return None, None, "payload selector variants are not witness-pattern safe"
        pattern = f"{state_decl.name} {{ {selector_field}: {selector_sum.name}::{target}, .. }}"
        assertion = (
            f"assert!(matches!({call}, Ok({pattern})));"
            if is_result
            else f"assert!(matches!({call}, {pattern}));"
        )

    rust = "\n".join(
        [
            "    #[test]",
            f"    fn {test_name}() {{",
            f"        {assertion}",
            "    }",
            "",
        ]
    )
    return test_name, rust, None


def build_machine_witnesses(
    program: Program,
    machines: Sequence[MachineDecl],
    coverages: Sequence[MachineCoverage],
    *,
    witness_limit: int = _DEFAULT_WITNESS_LIMIT,
) -> tuple[tuple[MachineWitnessReport, ...], str]:
    """Generate executable tests only from fully constructible concrete witnesses."""

    if witness_limit < 1:
        raise ValueError("witness_limit must be positive")
    by_machine = {coverage.machine: coverage for coverage in coverages}
    domain = _FiniteDomain(program, witness_limit)
    reports: list[MachineWitnessReport] = []
    rust_tests: list[str] = []

    for machine in machines:
        coverage = by_machine.get(machine.name)
        if coverage is None:
            reports.append(
                MachineWitnessReport(
                    machine.name,
                    0,
                    0,
                    False,
                    "coverage result is unavailable",
                    (),
                )
            )
            continue
        case_reports: list[MachineWitnessCaseReport] = []
        for case in coverage.cases:
            test_name, rust, reason = _case_test(
                program,
                machine,
                coverage,
                case,
                domain,
            )
            generated = rust is not None and test_name is not None
            case_reports.append(
                MachineWitnessCaseReport(
                    case.index,
                    test_name,
                    generated,
                    reason,
                )
            )
            if rust is not None:
                rust_tests.append(rust)
        generated_count = sum(item.generated for item in case_reports)
        skipped_count = len(case_reports) - generated_count
        report_reason = None
        if generated_count == 0:
            reasons = sorted(
                {
                    item.reason
                    for item in case_reports
                    if item.reason is not None
                }
            )
            report_reason = "; ".join(reasons) if reasons else "no concrete coverage cases"
        reports.append(
            MachineWitnessReport(
                machine.name,
                generated_count,
                skipped_count,
                generated_count > 0 and skipped_count == 0,
                report_reason,
                tuple(case_reports),
            )
        )

    lines = [
        "// @generated by Glyph machine coverage. Do not edit by hand.",
        "// Tests are emitted only for fully constructible state/input witnesses.",
        "use crate::generated::*;",
        "",
    ]
    if rust_tests:
        lines.extend(
            [
                "#[cfg(test)]",
                "mod glyph_machine_coverage_witnesses {",
                "    use super::*;",
                "",
                *rust_tests,
                "}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "// No executable witness tests were safe to generate.",
                "",
            ]
        )
    return tuple(reports), "\n".join(lines).rstrip() + "\n"


def machine_witness_payload(
    reports: Sequence[MachineWitnessReport],
) -> list[dict[str, object]]:
    return [asdict(report) for report in reports]

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from .compiler import CallExpr, GlyphError, Program, RustGenerator
from .machine import MachineDecl
from .machine_coverage import MachineCoverage, MachineCoverageCase, _machine_parts
from .machine_coverage_witness import _argument_rust, _resolve_alias


_RESULT_NAMES = {"R", "Result"}


@dataclass(frozen=True)
class MachineScenarioCaseReport:
    target_state: str
    test_name: str | None
    generated: bool
    steps: int
    case_indices: tuple[int, ...]
    reason: str | None


@dataclass(frozen=True)
class MachineScenarioReport:
    machine: str
    generated_tests: int
    skipped_targets: int
    max_steps: int
    complete: bool
    reason: str | None
    scenarios: tuple[MachineScenarioCaseReport, ...]


@dataclass(frozen=True)
class _ScenarioStep:
    source: str
    target: str
    case_index: int
    call: str
    is_result: bool


def _snake(name: str) -> str:
    out: list[str] = []
    for index, ch in enumerate(name):
        if ch.isupper() and index and not name[index - 1].isupper():
            out.append("_")
        out.append(ch.lower() if ch.isalnum() else "_")
    return "".join(out).strip("_") or "machine"


def _variant_name(value: str | None) -> str | None:
    if not value:
        return None
    tail = value.rsplit("::", 1)[-1].strip()
    for delimiter in ("(", "{", " "):
        if delimiter in tail:
            tail = tail.split(delimiter, 1)[0]
    return tail or None


def _variant_is_pattern_safe(selector_sum: object, name: str) -> bool:
    variants = getattr(selector_sum, "variants", ())
    variant = next((item for item in variants if item.name == name), None)
    return bool(variant is not None and not variant.tuple_types and not variant.fields)


def _step_for_case(
    program: Program,
    machine: MachineDecl,
    case: MachineCoverageCase,
) -> tuple[_ScenarioStep | None, str | None]:
    parts = _machine_parts(program, machine)
    if parts is None:
        return None, "selector or next function could not be resolved"
    state_decl, _, _, selector_sum, next_decl = parts
    if case.outcome not in {"defined", "fallthrough"}:
        return None, f"{case.outcome} is not a successful definite transition"
    source = _variant_name(case.selector)
    target = _variant_name(case.target_state)
    if source is None or target is None:
        return None, "source or target selector is not structurally known"
    if not _variant_is_pattern_safe(selector_sum, target):
        return None, "payload selector variants are not scenario-pattern safe"

    next_call = machine.next_expr
    if not isinstance(next_call, CallExpr):
        return None, "machine next expression is not a direct call"
    input_values: Mapping[str, str] = {
        binding.name: binding.value for binding in case.inputs
    }
    arguments: list[str] = []
    for argument in next_call.args:
        rendered = _argument_rust(argument, machine, "state", input_values)
        if rendered is None:
            return None, "next-call arguments are not direct state/input values or literals"
        arguments.append(rendered)

    return_type = _resolve_alias(program, next_decl.return_type)
    is_result = return_type.name in _RESULT_NAMES and len(return_type.args) == 2
    returns_state = (
        is_result
        and _resolve_alias(program, return_type.args[0]).name == state_decl.name
    ) or (not is_result and return_type.name == state_decl.name)
    if not returns_state:
        return None, "next function does not return State or Result<State, E>"

    return (
        _ScenarioStep(
            source,
            target,
            case.index,
            f"{next_decl.name}({', '.join(arguments)})",
            is_result,
        ),
        None,
    )


def _shortest_path(
    initial: str,
    target: str,
    adjacency: Mapping[str, Sequence[_ScenarioStep]],
) -> tuple[_ScenarioStep, ...] | None:
    pending: deque[tuple[str, tuple[_ScenarioStep, ...]]] = deque([(initial, ())])
    visited = {initial}
    while pending:
        state, path = pending.popleft()
        for step in adjacency.get(state, ()):
            next_path = (*path, step)
            if step.target == target:
                return next_path
            if step.target in visited:
                continue
            visited.add(step.target)
            pending.append((step.target, next_path))
    return None


def _render_scenario(
    program: Program,
    machine: MachineDecl,
    state_decl: object,
    selector_field: str,
    selector_sum: object,
    initial: str,
    target: str,
    path: Sequence[_ScenarioStep],
) -> tuple[str | None, str | None, str | None]:
    if not _variant_is_pattern_safe(selector_sum, initial):
        return None, None, "initial selector variant is not scenario-pattern safe"
    try:
        initial_rust = RustGenerator(program)._expr(machine.initial)
    except (GlyphError, TypeError) as exc:
        return None, None, f"machine init cannot be rendered safely: {exc}"

    state_name = getattr(state_decl, "name", machine.state_param.ty.name)
    selector_name = getattr(selector_sum, "name", "Selector")
    test_name = f"scenario_{_snake(machine.name)}_to_{_snake(target)}"
    lines = [
        "    #[test]",
        f"    fn {test_name}() {{",
        f"        let state = {initial_rust};",
        (
            "        assert!(matches!(&state, "
            f"{state_name} {{ {selector_field}: {selector_name}::{initial}, .. }}));"
        ),
    ]
    for index, step in enumerate(path, start=1):
        if step.is_result:
            lines.extend(
                [
                    f"        let state = match {step.call} {{",
                    "            Ok(state) => state,",
                    (
                        "            Err(_) => panic!(\"generated scenario step "
                        f"{index} unexpectedly rejected\"),"
                    ),
                    "        };",
                ]
            )
        else:
            lines.append(f"        let state = {step.call};")
        lines.append(
            "        assert!(matches!(&state, "
            f"{state_name} {{ {selector_field}: {selector_name}::{step.target}, .. }}));"
        )
    lines.extend(["    }", ""])
    return test_name, "\n".join(lines), None


def build_machine_scenarios(
    program: Program,
    machines: Sequence[MachineDecl],
    coverages: Sequence[MachineCoverage],
) -> tuple[tuple[MachineScenarioReport, ...], str]:
    """Generate shortest executable paths from machine.init over definite edges."""

    by_machine = {coverage.machine: coverage for coverage in coverages}
    reports: list[MachineScenarioReport] = []
    rust_tests: list[str] = []

    for machine in machines:
        coverage = by_machine.get(machine.name)
        parts = _machine_parts(program, machine)
        reachability = getattr(coverage, "state_reachability", None) if coverage else None
        if coverage is None or parts is None or reachability is None:
            reports.append(
                MachineScenarioReport(
                    machine.name,
                    0,
                    0,
                    0,
                    False,
                    "coverage, selector metadata, or state reachability is unavailable",
                    (),
                )
            )
            continue

        state_decl, _, selector_field, selector_sum, _ = parts
        initial = reachability.initial_state
        if initial is None:
            reports.append(
                MachineScenarioReport(
                    machine.name,
                    0,
                    0,
                    0,
                    False,
                    "machine initial selector is unavailable",
                    (),
                )
            )
            continue

        adjacency: dict[str, list[_ScenarioStep]] = {}
        unsafe_reasons: set[str] = set()
        for case in sorted(coverage.cases, key=lambda item: item.index):
            step, reason = _step_for_case(program, machine, case)
            if step is None:
                if reason is not None and case.outcome in {"defined", "fallthrough"}:
                    unsafe_reasons.add(reason)
                continue
            adjacency.setdefault(step.source, []).append(step)
        for steps in adjacency.values():
            steps.sort(key=lambda item: (item.case_index, item.target))

        scenario_reports: list[MachineScenarioCaseReport] = []
        targets = tuple(
            state
            for state in reachability.definitely_reachable
            if state != initial
        )
        for target in targets:
            path = _shortest_path(initial, target, adjacency)
            if path is None:
                reason = "no fully executable definite path from init"
                if unsafe_reasons:
                    reason += ": " + "; ".join(sorted(unsafe_reasons))
                scenario_reports.append(
                    MachineScenarioCaseReport(target, None, False, 0, (), reason)
                )
                continue
            test_name, rust, reason = _render_scenario(
                program,
                machine,
                state_decl,
                selector_field,
                selector_sum,
                initial,
                target,
                path,
            )
            generated = test_name is not None and rust is not None
            scenario_reports.append(
                MachineScenarioCaseReport(
                    target,
                    test_name,
                    generated,
                    len(path),
                    tuple(step.case_index for step in path),
                    reason,
                )
            )
            if rust is not None:
                rust_tests.append(rust)

        generated_count = sum(item.generated for item in scenario_reports)
        skipped_count = len(scenario_reports) - generated_count
        max_steps = max((item.steps for item in scenario_reports if item.generated), default=0)
        report_reason = None
        if not targets:
            report_reason = "no non-initial definitely reachable selector states"
        elif generated_count == 0:
            report_reason = "; ".join(
                sorted({item.reason for item in scenario_reports if item.reason})
            ) or "no executable scenario path"
        reports.append(
            MachineScenarioReport(
                machine.name,
                generated_count,
                skipped_count,
                max_steps,
                skipped_count == 0,
                report_reason,
                tuple(scenario_reports),
            )
        )

    lines = [
        "// @generated by Glyph machine scenario coverage. Do not edit by hand.",
        "// Each test replays a shortest definite path from machine.init.",
        "use crate::generated::*;",
        "",
    ]
    if rust_tests:
        lines.extend(
            [
                "#[cfg(test)]",
                "mod glyph_machine_scenario_witnesses {",
                "    use super::*;",
                "",
                *rust_tests,
                "}",
                "",
            ]
        )
    else:
        lines.extend(["// No executable multi-step scenarios were safe to generate.", ""])
    return tuple(reports), "\n".join(lines).rstrip() + "\n"


def machine_scenario_payload(
    reports: Sequence[MachineScenarioReport],
) -> list[dict[str, object]]:
    return [asdict(report) for report in reports]

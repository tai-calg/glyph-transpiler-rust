from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .compiler import CallExpr, FieldExpr, NameExpr, ProductDecl, Program, SumDecl
from .machine import MachineDecl
from .machine_coverage import MachineCoverage


@dataclass(frozen=True)
class MachineStateEdge:
    source: str
    target: str
    certainty: str
    reason: str
    case_indices: tuple[int, ...] = ()


@dataclass(frozen=True)
class MachineStateReachability:
    machine: str
    selector_type: str | None
    initial_state: str | None
    states: tuple[str, ...]
    definitely_reachable: tuple[str, ...]
    maybe_reachable: tuple[str, ...]
    definitely_unreachable: tuple[str, ...]
    definite_edges: tuple[MachineStateEdge, ...]
    possible_edges: tuple[MachineStateEdge, ...]
    exact: bool
    reason: str | None
    line: int


@dataclass(frozen=True)
class MachineStateReachabilityDiagnostic:
    code: str
    severity: str
    message: str
    subject: str
    line: int


def _variant_name(value: str | None) -> str | None:
    if not value:
        return None
    tail = value.rsplit("::", 1)[-1].strip()
    for delimiter in ("(", "{", " "):
        if delimiter in tail:
            tail = tail.split(delimiter, 1)[0]
    return tail or None


def _machine_selector_info(
    program: Program,
    machine: MachineDecl,
) -> tuple[tuple[str, ...], str, str] | None:
    products = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, ProductDecl)
    }
    sums = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, SumDecl)
    }
    state = products.get(machine.state_param.ty.name)
    if state is None or not isinstance(machine.selector, FieldExpr):
        return None
    selector_index = next(
        (
            index
            for index, field in enumerate(state.fields)
            if field.name == machine.selector.field
        ),
        None,
    )
    if selector_index is None:
        return None
    selector_type = state.fields[selector_index].ty
    selector_sum = sums.get(selector_type.name)
    if selector_sum is None:
        return None
    if not isinstance(machine.initial, CallExpr):
        return None
    if selector_index >= len(machine.initial.args):
        return None
    initial_expr = machine.initial.args[selector_index]
    if not isinstance(initial_expr, NameExpr):
        return None
    states = tuple(variant.name for variant in selector_sum.variants)
    if initial_expr.name not in states:
        return None
    return states, selector_sum.name, initial_expr.name


def _coverage_for_machine(
    coverages: Sequence[MachineCoverage],
    machine: str,
) -> MachineCoverage | None:
    return next((item for item in coverages if item.machine == machine), None)


def _edge_rows(
    rows: dict[tuple[str, str, str, str], list[int]],
) -> tuple[MachineStateEdge, ...]:
    return tuple(
        MachineStateEdge(
            source=source,
            target=target,
            certainty=certainty,
            reason=reason,
            case_indices=tuple(indices),
        )
        for (source, target, certainty, reason), indices in sorted(rows.items())
    )


def _reachable(
    initial: str,
    states: Sequence[str],
    edges: Sequence[MachineStateEdge],
) -> set[str]:
    adjacency: dict[str, set[str]] = {state: set() for state in states}
    for edge in edges:
        if edge.source in adjacency and edge.target in adjacency:
            adjacency[edge.source].add(edge.target)
    visited = {initial}
    pending = [initial]
    while pending:
        source = pending.pop()
        for target in adjacency.get(source, ()):
            if target in visited:
                continue
            visited.add(target)
            pending.append(target)
    return visited


def _ordered(states: Sequence[str], selected: set[str]) -> tuple[str, ...]:
    return tuple(state for state in states if state in selected)


def _unknown_result(
    machine: MachineDecl,
    selector_type: str | None,
    initial: str | None,
    states: tuple[str, ...],
    reason: str,
) -> MachineStateReachability:
    definite = (initial,) if initial is not None else ()
    maybe = tuple(state for state in states if state != initial)
    return MachineStateReachability(
        machine=machine.name,
        selector_type=selector_type,
        initial_state=initial,
        states=states,
        definitely_reachable=definite,
        maybe_reachable=maybe,
        definitely_unreachable=(),
        definite_edges=(),
        possible_edges=(),
        exact=False,
        reason=reason,
        line=machine.line,
    )


def build_machine_state_reachability(
    program: Program,
    machines: Sequence[MachineDecl],
    coverages: Sequence[MachineCoverage],
) -> tuple[MachineStateReachability, ...]:
    results: list[MachineStateReachability] = []
    for machine in machines:
        info = _machine_selector_info(program, machine)
        if info is None:
            results.append(
                _unknown_result(
                    machine,
                    None,
                    None,
                    (),
                    "selector states or initial state could not be resolved",
                )
            )
            continue
        states, selector_type, initial = info
        coverage = _coverage_for_machine(coverages, machine.name)
        if coverage is None:
            results.append(
                _unknown_result(
                    machine,
                    selector_type,
                    initial,
                    states,
                    "machine coverage is not available",
                )
            )
            continue

        definite_rows: dict[tuple[str, str, str, str], list[int]] = {}
        possible_rows: dict[tuple[str, str, str, str], list[int]] = {}
        precision_reasons: set[str] = set()

        def add(
            table: dict[tuple[str, str, str, str], list[int]],
            source: str,
            target: str,
            certainty: str,
            reason: str,
            case_index: int,
        ) -> None:
            table.setdefault((source, target, certainty, reason), []).append(case_index)

        if not coverage.cases:
            reason = coverage.reason or "coverage has no usable case matrix"
            precision_reasons.add(reason)
            for target in states:
                add(
                    possible_rows,
                    initial,
                    target,
                    "possible",
                    reason,
                    -1,
                )
        else:
            for case in coverage.cases:
                source = _variant_name(case.selector)
                if source not in states:
                    precision_reasons.add("a coverage source selector could not be resolved")
                    for target in states:
                        add(
                            possible_rows,
                            initial,
                            target,
                            "possible",
                            "unresolved coverage source selector",
                            case.index,
                        )
                    continue

                if case.outcome in {"defined", "fallthrough"}:
                    target = _variant_name(case.target_state)
                    if target in states:
                        add(
                            definite_rows,
                            source,
                            target,
                            "definite",
                            "selected successful transition",
                            case.index,
                        )
                    else:
                        precision_reasons.add(
                            "one or more successful branches have an unknown target selector"
                        )
                        for possible_target in states:
                            add(
                                possible_rows,
                                source,
                                possible_target,
                                "possible",
                                "successful transition target is unknown",
                                case.index,
                            )
                elif case.outcome == "unknown":
                    precision_reasons.add(
                        "one or more coverage rows have unknown ordered-guard selection"
                    )
                    for target in states:
                        add(
                            possible_rows,
                            source,
                            target,
                            "possible",
                            "coverage row outcome is unknown",
                            case.index,
                        )
                # Explicit rejection and missing behavior contribute no state edge.

        definite_edges = _edge_rows(definite_rows)
        possible_edges = _edge_rows(possible_rows)
        definitely_reachable_set = _reachable(initial, states, definite_edges)
        possibly_reachable_set = _reachable(
            initial,
            states,
            (*definite_edges, *possible_edges),
        )
        maybe_reachable_set = possibly_reachable_set - definitely_reachable_set
        definitely_unreachable_set = set(states) - possibly_reachable_set
        exact = bool(coverage.exact and not possible_edges and not precision_reasons)
        reason = "; ".join(sorted(precision_reasons)) or None

        results.append(
            MachineStateReachability(
                machine=machine.name,
                selector_type=selector_type,
                initial_state=initial,
                states=states,
                definitely_reachable=_ordered(states, definitely_reachable_set),
                maybe_reachable=_ordered(states, maybe_reachable_set),
                definitely_unreachable=_ordered(states, definitely_unreachable_set),
                definite_edges=definite_edges,
                possible_edges=possible_edges,
                exact=exact,
                reason=reason,
                line=machine.line,
            )
        )
    return tuple(results)


def build_machine_state_reachability_diagnostics(
    results: Sequence[MachineStateReachability],
) -> tuple[MachineStateReachabilityDiagnostic, ...]:
    diagnostics: list[MachineStateReachabilityDiagnostic] = []
    for result in results:
        if not result.definitely_unreachable:
            continue
        initial = result.initial_state or "?"
        states = ", ".join(f"`{state}`" for state in result.definitely_unreachable)
        diagnostics.append(
            MachineStateReachabilityDiagnostic(
                code="machine-state-unreachable",
                severity="warning",
                message=(
                    f"machine `{result.machine}` のselector state {states} は"
                    f" init `{initial}` から到達できない"
                ),
                subject=result.machine,
                line=result.line,
            )
        )
    return tuple(diagnostics)

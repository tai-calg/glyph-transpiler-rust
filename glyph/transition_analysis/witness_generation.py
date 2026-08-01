from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..artifacts import CompilationModel
from ..compiler import FunctionDecl
from .analysis_evidence import (
    VerifiedReachabilityWitness,
    verified_reachability_witness,
)
from .concrete import ConcreteExecutionError, ConcreteInterpreter
from .effect_contract import VerifiedEffectContractRegistry
from .finite_domain import FiniteDomainError, finite_assignments


WITNESS_GENERATION_VERSION = 2


@dataclass(frozen=True)
class WitnessGenerationIssue:
    entry: str
    code: str
    detail: str

    def to_ir(self) -> dict[str, str]:
        return {
            "entry": self.entry,
            "code": self.code,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class TargetedWitnessCase:
    """One reviewed concrete input used only as an existence witness.

    A targeted case does not claim exhaustive input coverage. Its source must identify
    why the concrete input is trusted and reproducible.
    """

    entry: str
    arguments: tuple[object, ...]
    source: str
    label: str = ""

    def __post_init__(self) -> None:
        if not self.entry.strip():
            raise ValueError("targeted witness entry must not be empty")
        if not self.source.strip():
            raise ValueError("targeted witness source must not be empty")

    def to_ir(self) -> dict[str, object]:
        return {
            "entry": self.entry,
            "arguments": [repr(value) for value in self.arguments],
            "source": self.source,
            "label": self.label or None,
        }


@dataclass(frozen=True)
class TargetedWitnessRegistry:
    cases: tuple[TargetedWitnessCase, ...] = ()

    def __post_init__(self) -> None:
        seen: set[tuple[str, str]] = set()
        for case in self.cases:
            key = (case.entry, repr(case.arguments))
            if key in seen:
                raise ValueError(
                    f"duplicate targeted witness input for {case.entry}: {case.arguments!r}"
                )
            seen.add(key)

    def cases_for(self, entry: str) -> tuple[TargetedWitnessCase, ...]:
        return tuple(case for case in self.cases if case.entry == entry)

    def to_ir(self) -> dict[str, object]:
        return {
            "cases": [case.to_ir() for case in self.cases],
        }


@dataclass(frozen=True)
class GeneratedWitness:
    entry: str
    edge_id: str
    completion: str
    witness: VerifiedReachabilityWitness
    generation_strategy: str = "finite-exhaustive"
    case_source: str | None = None

    def to_ir(self) -> dict[str, object]:
        return {
            "entry": self.entry,
            "edge_id": self.edge_id,
            "completion": self.completion,
            "generation_strategy": self.generation_strategy,
            "case_source": self.case_source,
            "witness": self.witness.to_ir(),
        }


@dataclass(frozen=True)
class WitnessEntryCoverage:
    entry: str
    strategy: str
    exhaustive: bool
    requested_case_count: int
    completed_case_count: int

    def to_ir(self) -> dict[str, object]:
        return {
            "entry": self.entry,
            "strategy": self.strategy,
            "exhaustive": self.exhaustive,
            "requested_case_count": self.requested_case_count,
            "completed_case_count": self.completed_case_count,
        }


@dataclass(frozen=True)
class BoundedWitnessGenerationReport:
    entries: tuple[str, ...]
    max_cases_per_entry: int
    attempted_case_count: int
    completed_case_count: int
    witnesses: tuple[GeneratedWitness, ...]
    issues: tuple[WitnessGenerationIssue, ...]
    entry_coverage: tuple[WitnessEntryCoverage, ...] = ()

    @property
    def complete(self) -> bool:
        covered_entries = {item.entry for item in self.entry_coverage}
        return (
            not self.issues
            and self.attempted_case_count == self.completed_case_count
            and covered_entries == set(self.entries)
            and all(item.requested_case_count > 0 for item in self.entry_coverage)
        )

    @property
    def exhaustive(self) -> bool:
        return self.complete and all(item.exhaustive for item in self.entry_coverage)

    def witness_for(
        self,
        entry: str,
        edge_id: str,
        completion_filter: frozenset[str] | None = None,
    ) -> VerifiedReachabilityWitness | None:
        for item in self.witnesses:
            if item.entry != entry or item.edge_id != edge_id:
                continue
            if completion_filter is not None and item.completion not in completion_filter:
                continue
            return item.witness
        return None

    def to_ir(self) -> dict[str, object]:
        return {
            "version": WITNESS_GENERATION_VERSION,
            "enabled": True,
            "complete": self.complete,
            "exhaustive": self.exhaustive,
            "entries": list(self.entries),
            "max_cases_per_entry": self.max_cases_per_entry,
            "attempted_case_count": self.attempted_case_count,
            "completed_case_count": self.completed_case_count,
            "witness_count": len(self.witnesses),
            "entry_coverage": [item.to_ir() for item in self.entry_coverage],
            "witnesses": [item.to_ir() for item in self.witnesses],
            "issues": [item.to_ir() for item in self.issues],
        }


def disabled_witness_generation_ir() -> dict[str, object]:
    return {
        "version": WITNESS_GENERATION_VERSION,
        "enabled": False,
        "complete": False,
        "exhaustive": False,
        "entries": [],
        "max_cases_per_entry": 0,
        "attempted_case_count": 0,
        "completed_case_count": 0,
        "witness_count": 0,
        "entry_coverage": [],
        "witnesses": [],
        "issues": [],
    }


def generate_bounded_system_witnesses(
    model: CompilationModel,
    entries: Iterable[str],
    contracts: VerifiedEffectContractRegistry,
    *,
    max_cases_per_entry: int = 4096,
    targeted_witnesses: TargetedWitnessRegistry | None = None,
) -> BoundedWitnessGenerationReport:
    """Generate concrete same-edge existence witnesses.

    Finite Bool/Product/Sum entries are exhausted when they fit the budget. If the
    domain is unsupported or too large, explicitly reviewed targeted inputs may be
    used instead. Targeted inputs prove only existence; they never claim exhaustive
    input coverage. Exact trace/completion claims still come from abstract Evidence.
    """

    if max_cases_per_entry <= 0:
        raise ValueError("witness case limit must be positive")

    selected_entries = tuple(sorted(set(entries)))
    declarations = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, FunctionDecl)
    }
    targeted_witnesses = targeted_witnesses or TargetedWitnessRegistry()
    attempted = 0
    completed = 0
    generated: dict[tuple[str, str, str], GeneratedWitness] = {}
    issues: list[WitnessGenerationIssue] = []
    coverage: list[WitnessEntryCoverage] = []

    for entry in selected_entries:
        declaration = declarations.get(entry)
        if declaration is None:
            issues.append(
                WitnessGenerationIssue(
                    entry,
                    "entry-declaration-unavailable",
                    f"System entry function {entry} is unavailable",
                )
            )
            continue

        variables = tuple(
            (parameter.name, parameter.ty) for parameter in declaration.params
        )
        strategy = "finite-exhaustive"
        exhaustive = True
        case_sources: list[str | None]
        try:
            assignments = finite_assignments(
                model,
                variables,
                max_cases=max_cases_per_entry,
            )
            argument_cases = tuple(
                tuple(assignment[parameter.name] for parameter in declaration.params)
                for assignment in assignments
            )
            case_sources = ["finite-domain-exhaustive"] * len(argument_cases)
        except FiniteDomainError as error:
            targeted = targeted_witnesses.cases_for(entry)
            if not targeted:
                issues.append(
                    WitnessGenerationIssue(entry, "finite-domain-unavailable", str(error))
                )
                continue
            strategy = "targeted-existence"
            exhaustive = False
            argument_cases = tuple(case.arguments for case in targeted)
            case_sources = [case.source for case in targeted]

        interpreter = ConcreteInterpreter(
            model,
            effect_handlers=contracts.handlers(entry),
        )
        entry_completed = 0
        entry_failed = False
        for arguments, case_source in zip(argument_cases, case_sources, strict=True):
            attempted += 1
            if len(arguments) != len(declaration.params):
                issues.append(
                    WitnessGenerationIssue(
                        entry,
                        "targeted-witness-arity-mismatch",
                        f"entry {entry} expects {len(declaration.params)} arguments, "
                        f"target supplies {len(arguments)}",
                    )
                )
                entry_failed = True
                break
            try:
                execution = interpreter.run(entry, arguments)
            except ConcreteExecutionError as error:
                issues.append(
                    WitnessGenerationIssue(entry, "concrete-replay-failed", str(error))
                )
                entry_failed = True
                break
            except Exception as error:
                issues.append(
                    WitnessGenerationIssue(
                        entry,
                        "effect-contract-handler-failed",
                        str(error) or type(error).__name__,
                    )
                )
                entry_failed = True
                break

            completed += 1
            entry_completed += 1
            for event in execution.transition_trace:
                key = (entry, event.edge_id, execution.completion)
                if key in generated:
                    continue
                witness = verified_reachability_witness(
                    execution,
                    arguments,
                    event.edge_id,
                )
                generated[key] = GeneratedWitness(
                    entry,
                    event.edge_id,
                    execution.completion,
                    witness,
                    generation_strategy=strategy,
                    case_source=case_source,
                )

        coverage.append(
            WitnessEntryCoverage(
                entry,
                strategy,
                exhaustive,
                len(argument_cases),
                entry_completed,
            )
        )
        if entry_failed:
            continue

    return BoundedWitnessGenerationReport(
        selected_entries,
        max_cases_per_entry,
        attempted,
        completed,
        tuple(generated[key] for key in sorted(generated)),
        tuple(issues),
        tuple(coverage),
    )


__all__ = [
    "BoundedWitnessGenerationReport",
    "GeneratedWitness",
    "TargetedWitnessCase",
    "TargetedWitnessRegistry",
    "WITNESS_GENERATION_VERSION",
    "WitnessEntryCoverage",
    "WitnessGenerationIssue",
    "disabled_witness_generation_ir",
    "generate_bounded_system_witnesses",
]

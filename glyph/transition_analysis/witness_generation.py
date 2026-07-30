from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from ..artifacts import CompilationModel
from ..compiler import FunctionDecl
from .analysis_evidence import (
    VerifiedReachabilityWitness,
    verified_reachability_witness,
)
from .concrete import ConcreteExecutionError, ConcreteInterpreter
from .effect_contract import VerifiedEffectContractRegistry
from .finite_domain import FiniteDomainError, finite_assignments


WITNESS_GENERATION_VERSION = 1


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
class GeneratedWitness:
    entry: str
    edge_id: str
    completion: str
    witness: VerifiedReachabilityWitness

    def to_ir(self) -> dict[str, object]:
        return {
            "entry": self.entry,
            "edge_id": self.edge_id,
            "completion": self.completion,
            "witness": self.witness.to_ir(),
        }


@dataclass(frozen=True)
class BoundedWitnessGenerationReport:
    entries: tuple[str, ...]
    max_cases_per_entry: int
    attempted_case_count: int
    completed_case_count: int
    witnesses: tuple[GeneratedWitness, ...]
    issues: tuple[WitnessGenerationIssue, ...]

    @property
    def complete(self) -> bool:
        return not self.issues and self.attempted_case_count == self.completed_case_count

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
            "entries": list(self.entries),
            "max_cases_per_entry": self.max_cases_per_entry,
            "attempted_case_count": self.attempted_case_count,
            "completed_case_count": self.completed_case_count,
            "witness_count": len(self.witnesses),
            "witnesses": [item.to_ir() for item in self.witnesses],
            "issues": [item.to_ir() for item in self.issues],
        }



def disabled_witness_generation_ir() -> dict[str, object]:
    return {
        "version": WITNESS_GENERATION_VERSION,
        "enabled": False,
        "complete": False,
        "entries": [],
        "max_cases_per_entry": 0,
        "attempted_case_count": 0,
        "completed_case_count": 0,
        "witness_count": 0,
        "witnesses": [],
        "issues": [],
    }



def generate_bounded_system_witnesses(
    model: CompilationModel,
    entries: Iterable[str],
    contracts: VerifiedEffectContractRegistry,
    *,
    max_cases_per_entry: int = 4096,
) -> BoundedWitnessGenerationReport:
    """Exhaust finite System-entry inputs and retain concrete same-edge witnesses.

    Only reviewed handlers from ``contracts`` are exposed to the interpreter.  A
    missing Effect contract, non-finite input domain, execution failure or budget
    overflow makes the campaign incomplete; none is converted into a witness.
    Successfully replayed cases remain valid existence witnesses even when another
    entry is incomplete.
    """

    if max_cases_per_entry <= 0:
        raise ValueError("witness case limit must be positive")

    selected_entries = tuple(sorted(set(entries)))
    declarations = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, FunctionDecl)
    }
    attempted = 0
    completed = 0
    generated: dict[tuple[str, str, str], GeneratedWitness] = {}
    issues: list[WitnessGenerationIssue] = []

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
        try:
            assignments = finite_assignments(
                model,
                variables,
                max_cases=max_cases_per_entry,
            )
        except FiniteDomainError as error:
            issues.append(
                WitnessGenerationIssue(entry, "finite-domain-unavailable", str(error))
            )
            continue

        interpreter = ConcreteInterpreter(
            model,
            effect_handlers=contracts.handlers(entry),
        )
        entry_failed = False
        for assignment in assignments:
            attempted += 1
            arguments = tuple(
                assignment[parameter.name] for parameter in declaration.params
            )
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
    )


__all__ = [
    "BoundedWitnessGenerationReport",
    "GeneratedWitness",
    "WITNESS_GENERATION_VERSION",
    "WitnessGenerationIssue",
    "disabled_witness_generation_ir",
    "generate_bounded_system_witnesses",
]

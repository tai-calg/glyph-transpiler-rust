from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..artifacts import CompilationModel
from ..compiler import FunctionDecl
from .abstract_coverage import abstract_store_covers, abstract_value_covers
from .abstract_solver import AbstractInterpreter
from .abstract_state import AbstractAnalysisResult, GuardedAlternative
from .concrete import ConcreteExecutionResult, ConcreteInterpreter, EffectHandler
from .effect_summary import EffectSummary
from .finite_domain import FiniteDomainError, finite_assignments, finite_values
from .reference import ReferenceInterpreter


@dataclass(frozen=True)
class OracleCase:
    arguments: tuple[object, ...]
    reference: ConcreteExecutionResult
    teir: ConcreteExecutionResult

    @property
    def matches(self) -> bool:
        return self.reference == self.teir


@dataclass(frozen=True)
class BoundedOracleReport:
    function: str
    cases: tuple[OracleCase, ...]

    @property
    def mismatches(self) -> tuple[OracleCase, ...]:
        return tuple(case for case in self.cases if not case.matches)

    @property
    def exact(self) -> bool:
        return not self.mismatches


@dataclass(frozen=True)
class AbstractCoverageCase:
    arguments: tuple[object, ...]
    concrete: ConcreteExecutionResult
    covered: bool
    trace_covered: bool
    return_covered: bool
    store_covered: bool


@dataclass(frozen=True)
class BoundedSoundnessReport:
    function: str
    abstract: AbstractAnalysisResult
    cases: tuple[AbstractCoverageCase, ...]

    @property
    def uncovered(self) -> tuple[AbstractCoverageCase, ...]:
        return tuple(case for case in self.cases if not case.covered)

    @property
    def sound_for_bounded_domain(self) -> bool:
        return not self.uncovered


def compare_bounded_ast_and_teir(
    model: CompilationModel,
    function_name: str,
    *,
    effect_handlers: Mapping[str, EffectHandler] | None = None,
    max_cases: int = 4096,
) -> BoundedOracleReport:
    declaration, argument_cases = _finite_argument_cases(
        model,
        function_name,
        max_cases=max_cases,
    )
    del declaration
    handlers = dict(effect_handlers or {})
    cases = tuple(
        OracleCase(
            tuple(arguments),
            ReferenceInterpreter(model, effect_handlers=handlers).run(
                function_name,
                arguments,
            ),
            ConcreteInterpreter(model, effect_handlers=handlers).run(
                function_name,
                arguments,
            ),
        )
        for arguments in argument_cases
    )
    return BoundedOracleReport(function_name, cases)


def compare_bounded_teir_and_abstract(
    model: CompilationModel,
    function_name: str,
    *,
    effect_handlers: Mapping[str, EffectHandler] | None = None,
    effect_summaries: Mapping[str, EffectSummary] | None = None,
    max_cases: int = 4096,
) -> BoundedSoundnessReport:
    """Check bounded inclusion of traces, completion, return/error and final store."""

    declaration, argument_cases = _finite_argument_cases(
        model,
        function_name,
        max_cases=max_cases,
    )
    abstract = AbstractInterpreter(
        model,
        effect_summaries=effect_summaries,
    ).analyze(function_name)
    handlers = dict(effect_handlers or {})
    parameter_names = tuple(parameter.name for parameter in declaration.params)
    cases: list[AbstractCoverageCase] = []

    for arguments in argument_cases:
        concrete = ConcreteInterpreter(
            model,
            effect_handlers=handlers,
        ).run(function_name, arguments)
        inputs = dict(zip(parameter_names, arguments, strict=True))
        coverage = tuple(
            _alternative_coverage(
                alternative,
                concrete,
                inputs,
                input_context=function_name,
            )
            for alternative in abstract.completed
        )
        trace_covered = any(item[0] for item in coverage)
        return_covered = any(item[0] and item[1] for item in coverage)
        store_covered = any(item[0] and item[1] and item[2] for item in coverage)
        cases.append(
            AbstractCoverageCase(
                tuple(arguments),
                concrete,
                trace_covered and return_covered and store_covered,
                trace_covered,
                return_covered,
                store_covered,
            )
        )
    return BoundedSoundnessReport(function_name, abstract, tuple(cases))


def _alternative_coverage(
    alternative: GuardedAlternative,
    concrete: ConcreteExecutionResult,
    inputs: Mapping[str, object],
    *,
    input_context: str,
) -> tuple[bool, bool, bool]:
    if (
        concrete.completion not in alternative.completion
        and "unknown" not in alternative.completion
    ):
        return False, False, False

    concrete_edges = tuple(event.edge_id for event in concrete.transition_trace)
    abstract_edges = tuple(event.edge_id for event in alternative.transition_trace)
    if not alternative.transition_trace_top and concrete_edges != abstract_edges:
        return False, False, False

    concrete_effects = tuple(event.operation for event in concrete.effect_trace)
    abstract_effects = tuple(event.operation for event in alternative.effect_trace)
    if not alternative.effect_trace_top and concrete_effects != abstract_effects:
        return False, False, False

    expected = (
        concrete.error
        if concrete.completion == "propagated-failure"
        else concrete.return_value
    )
    return_covered = abstract_value_covers(
        alternative.return_value,
        expected,
        inputs,
        input_context=input_context,
    )
    store_covered = abstract_store_covers(
        alternative,
        getattr(concrete, "final_store", ()),
        inputs,
        input_context=input_context,
    )
    return True, return_covered, store_covered


def _finite_argument_cases(
    model: CompilationModel,
    function_name: str,
    *,
    max_cases: int,
) -> tuple[FunctionDecl, tuple[tuple[object, ...], ...]]:
    declaration = next(
        (
            item
            for item in model.program.declarations
            if isinstance(item, FunctionDecl) and item.name == function_name
        ),
        None,
    )
    if declaration is None:
        raise FiniteDomainError(f"unknown function {function_name}")
    variables = tuple((parameter.name, parameter.ty) for parameter in declaration.params)
    assignments = finite_assignments(model, variables, max_cases=max_cases)
    return declaration, tuple(
        tuple(assignment[parameter.name] for parameter in declaration.params)
        for assignment in assignments
    )


__all__ = [
    "AbstractCoverageCase",
    "BoundedOracleReport",
    "BoundedSoundnessReport",
    "FiniteDomainError",
    "OracleCase",
    "compare_bounded_ast_and_teir",
    "compare_bounded_teir_and_abstract",
    "finite_values",
]

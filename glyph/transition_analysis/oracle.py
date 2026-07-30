from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Mapping

from ..artifacts import CompilationModel
from ..compiler import FunctionDecl, ProductDecl, SumDecl, TypeRef
from .abstract_solver import AbstractInterpreter
from .abstract_state import AbstractAnalysisResult, GuardedAlternative
from .concrete import (
    ConcreteExecutionResult,
    ConcreteInterpreter,
    ConstructorValue,
    EffectHandler,
    VariantValue,
)
from .effect_summary import EffectSummary
from .reference import ReferenceInterpreter


class FiniteDomainError(ValueError):
    pass


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
    """Exhaustively compare source control flow and TEIR for finite inputs."""

    argument_cases = _finite_argument_cases(model, function_name, max_cases=max_cases)
    handlers = dict(effect_handlers or {})
    cases: list[OracleCase] = []
    for arguments in argument_cases:
        reference = ReferenceInterpreter(
            model,
            effect_handlers=handlers,
        ).run(function_name, arguments)
        teir = ConcreteInterpreter(
            model,
            effect_handlers=handlers,
        ).run(function_name, arguments)
        cases.append(OracleCase(tuple(arguments), reference, teir))
    return BoundedOracleReport(function_name, tuple(cases))


def compare_bounded_teir_and_abstract(
    model: CompilationModel,
    function_name: str,
    *,
    effect_handlers: Mapping[str, EffectHandler] | None = None,
    effect_summaries: Mapping[str, EffectSummary] | None = None,
    max_cases: int = 4096,
) -> BoundedSoundnessReport:
    """Check concrete trace/completion inclusion over one finite input domain.

    This is a bounded regression oracle, not a general proof. A concrete
    execution is covered when at least one abstract alternative admits its
    completion and exact transition/effect operation sequences, or explicitly
    carries a top trace.
    """

    argument_cases = _finite_argument_cases(model, function_name, max_cases=max_cases)
    abstract = AbstractInterpreter(
        model,
        effect_summaries=effect_summaries,
    ).analyze(function_name)
    handlers = dict(effect_handlers or {})
    cases: list[AbstractCoverageCase] = []
    for arguments in argument_cases:
        concrete = ConcreteInterpreter(
            model,
            effect_handlers=handlers,
        ).run(function_name, arguments)
        cases.append(
            AbstractCoverageCase(
                tuple(arguments),
                concrete,
                any(
                    _alternative_covers_concrete(alternative, concrete)
                    for alternative in abstract.completed
                ),
            )
        )
    return BoundedSoundnessReport(function_name, abstract, tuple(cases))


def _alternative_covers_concrete(
    alternative: GuardedAlternative,
    concrete: ConcreteExecutionResult,
) -> bool:
    completion = concrete.completion
    if completion not in alternative.completion and "unknown" not in alternative.completion:
        return False
    concrete_edges = tuple(event.edge_id for event in concrete.transition_trace)
    abstract_edges = tuple(event.edge_id for event in alternative.transition_trace)
    if not alternative.transition_trace_top and concrete_edges != abstract_edges:
        return False
    concrete_effects = tuple(event.operation for event in concrete.effect_trace)
    abstract_effects = tuple(event.operation for event in alternative.effect_trace)
    if not alternative.effect_trace_top and concrete_effects != abstract_effects:
        return False
    return True


def _finite_argument_cases(
    model: CompilationModel,
    function_name: str,
    *,
    max_cases: int,
) -> tuple[tuple[object, ...], ...]:
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
    domains = [finite_values(model, parameter.ty) for parameter in declaration.params]
    total = 1
    for domain in domains:
        total *= len(domain)
    if total > max_cases:
        raise FiniteDomainError(
            f"bounded oracle requires {total} cases, limit is {max_cases}"
        )
    return tuple(tuple(arguments) for arguments in product(*domains))


def finite_values(
    model: CompilationModel,
    type_ref: TypeRef,
    *,
    _visiting: frozenset[str] = frozenset(),
) -> tuple[object, ...]:
    """Enumerate one finite Glyph type without approximating recursive domains."""

    if type_ref.name in {"B", "bool"} and not type_ref.args:
        return (False, True)
    if type_ref.name in _visiting:
        raise FiniteDomainError(f"recursive finite domain is unsupported: {type_ref.name}")
    products = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, ProductDecl)
    }
    sums = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, SumDecl)
    }
    product_decl = products.get(type_ref.name)
    if product_decl is not None:
        visiting = _visiting | {type_ref.name}
        field_domains = [
            finite_values(model, field.ty, _visiting=visiting)
            for field in product_decl.fields
        ]
        return tuple(
            ConstructorValue(
                product_decl.name,
                tuple(
                    (field.name, value)
                    for field, value in zip(
                        product_decl.fields,
                        values,
                        strict=True,
                    )
                ),
            )
            for values in product(*field_domains)
        )
    sum_decl = sums.get(type_ref.name)
    if sum_decl is not None:
        visiting = _visiting | {type_ref.name}
        values: list[object] = []
        for variant in sum_decl.variants:
            argument_types = (
                tuple(field.ty for field in variant.fields)
                if variant.fields
                else variant.tuple_types
            )
            argument_domains = [
                finite_values(model, argument_type, _visiting=visiting)
                for argument_type in argument_types
            ]
            if not argument_domains:
                values.append(VariantValue(variant.name))
                continue
            values.extend(
                VariantValue(variant.name, tuple(arguments))
                for arguments in product(*argument_domains)
            )
        return tuple(values)
    raise FiniteDomainError(
        f"type {type_ref.name} is not a finite enumerable Bool/Product/Sum domain"
    )

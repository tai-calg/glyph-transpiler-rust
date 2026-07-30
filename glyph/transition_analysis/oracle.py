from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..artifacts import CompilationModel
from ..compiler import FunctionDecl
from .abstract_solver import AbstractInterpreter
from .abstract_state import AbstractAnalysisResult, GuardedAlternative
from .abstract_value import (
    AbstractValue,
    ApplicationValue,
    BottomValue,
    ConstantValue,
    ConstructorValue as AbstractConstructorValue,
    FieldValue,
    ParameterValue,
    PhiValue,
    TopValue,
)
from .concrete import (
    ConcreteExecutionResult,
    ConcreteInterpreter,
    ConstructorValue,
    EffectHandler,
    ResultValue,
    VariantValue,
)
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
    """Exhaustively compare source control flow and TEIR for finite inputs."""

    declaration, argument_cases = _finite_argument_cases(
        model,
        function_name,
        max_cases=max_cases,
    )
    del declaration
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
    """Check bounded concrete inclusion in RTAI outputs.

    Coverage includes completion, transition/effect operation sequences, return
    or propagated-error value, and the concrete final store when the concrete
    runtime exposes one.  This remains a bounded regression oracle rather than a
    proof for unbounded domains.
    """

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
    cases: list[AbstractCoverageCase] = []
    parameter_names = tuple(parameter.name for parameter in declaration.params)

    for arguments in argument_cases:
        concrete = ConcreteInterpreter(
            model,
            effect_handlers=handlers,
        ).run(function_name, arguments)
        inputs = dict(zip(parameter_names, arguments, strict=True))
        results = [
            _alternative_coverage(alternative, concrete, inputs)
            for alternative in abstract.completed
        ]
        trace_covered = any(item[0] for item in results)
        return_covered = any(item[0] and item[1] for item in results)
        store_covered = any(item[0] and item[1] and item[2] for item in results)
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
) -> tuple[bool, bool, bool]:
    completion = concrete.completion
    if completion not in alternative.completion and "unknown" not in alternative.completion:
        return False, False, False

    concrete_edges = tuple(event.edge_id for event in concrete.transition_trace)
    abstract_edges = tuple(event.edge_id for event in alternative.transition_trace)
    if not alternative.transition_trace_top and concrete_edges != abstract_edges:
        return False, False, False

    concrete_effects = tuple(event.operation for event in concrete.effect_trace)
    abstract_effects = tuple(event.operation for event in alternative.effect_trace)
    if not alternative.effect_trace_top and concrete_effects != abstract_effects:
        return False, False, False

    expected_value = (
        concrete.error
        if concrete.completion == "propagated-failure"
        else concrete.return_value
    )
    return_covered = _abstract_value_covers(
        alternative.return_value,
        expected_value,
        inputs,
    )
    store_covered = _abstract_store_covers(
        alternative,
        getattr(concrete, "final_store", ()),
        inputs,
    )
    return True, return_covered, store_covered


def _abstract_store_covers(
    alternative: GuardedAlternative,
    concrete_store: object,
    inputs: Mapping[str, object],
) -> bool:
    if concrete_store in (None, (), {}):
        return True
    if isinstance(concrete_store, Mapping):
        items = tuple(concrete_store.items())
    elif isinstance(concrete_store, tuple):
        items = concrete_store
    else:
        return alternative.store.approximation.kind.value == "unknown"

    abstract = {
        (location.kind, location.key): value
        for location, value in alternative.store.bindings
    }
    for raw_location, concrete_value in items:
        if isinstance(raw_location, tuple) and len(raw_location) == 2:
            key = (str(raw_location[0]), str(raw_location[1]))
        else:
            key = ("external", str(raw_location))
        value = abstract.get(key)
        if value is None:
            if alternative.store.approximation.kind.value == "unknown":
                continue
            return False
        if not _abstract_value_covers(value, concrete_value, inputs):
            return False
    return True


def _abstract_value_covers(
    value: AbstractValue | None,
    concrete: object,
    inputs: Mapping[str, object],
) -> bool:
    if value is None:
        return concrete is None
    if isinstance(value, TopValue):
        return True
    if isinstance(value, BottomValue):
        return False
    if isinstance(value, ConstantValue):
        return value.value == concrete
    if isinstance(value, ParameterValue):
        return value.name not in inputs or inputs[value.name] == concrete
    if isinstance(value, PhiValue):
        return any(
            _abstract_value_covers(item, concrete, inputs)
            for item in value.values
        )
    if isinstance(value, FieldValue):
        base = _concrete_from_abstract(value.base, inputs)
        if isinstance(base, ConstructorValue):
            try:
                return base.field(value.field) == concrete
            except Exception:
                return False
        return base is _UNKNOWN_CONCRETE
    if isinstance(value, AbstractConstructorValue):
        if isinstance(concrete, ConstructorValue):
            if value.type_name != concrete.type_name:
                return False
            concrete_fields = dict(concrete.fields)
            return all(
                field_name in concrete_fields
                and _abstract_value_covers(argument, concrete_fields[field_name], inputs)
                for field_name, argument in zip(
                    value.field_names,
                    value.arguments,
                    strict=True,
                )
            )
        if isinstance(concrete, VariantValue):
            return (
                value.type_name == concrete.name
                and len(value.arguments) == len(concrete.arguments)
                and all(
                    _abstract_value_covers(argument, item, inputs)
                    for argument, item in zip(
                        value.arguments,
                        concrete.arguments,
                        strict=True,
                    )
                )
            )
        return False
    if isinstance(value, ApplicationValue):
        evaluated = _concrete_from_abstract(value, inputs)
        if evaluated is _UNKNOWN_CONCRETE:
            return True
        return evaluated == concrete
    return True


_UNKNOWN_CONCRETE = object()


def _concrete_from_abstract(
    value: AbstractValue,
    inputs: Mapping[str, object],
) -> object:
    if isinstance(value, ConstantValue):
        return value.value
    if isinstance(value, ParameterValue):
        return inputs.get(value.name, _UNKNOWN_CONCRETE)
    if isinstance(value, FieldValue):
        base = _concrete_from_abstract(value.base, inputs)
        if isinstance(base, ConstructorValue):
            try:
                return base.field(value.field)
            except Exception:
                return _UNKNOWN_CONCRETE
        return _UNKNOWN_CONCRETE
    if isinstance(value, AbstractConstructorValue):
        arguments = tuple(
            _concrete_from_abstract(argument, inputs)
            for argument in value.arguments
        )
        if any(item is _UNKNOWN_CONCRETE for item in arguments):
            return _UNKNOWN_CONCRETE
        if value.field_names:
            return ConstructorValue(
                value.type_name,
                tuple(zip(value.field_names, arguments, strict=True)),
            )
        return VariantValue(value.type_name, arguments)
    if isinstance(value, ApplicationValue):
        arguments = tuple(
            _concrete_from_abstract(argument, inputs)
            for argument in value.arguments
        )
        if any(item is _UNKNOWN_CONCRETE for item in arguments):
            return _UNKNOWN_CONCRETE
        if value.operation in {"Ok", "Err"} and len(arguments) == 1:
            return ResultValue(value.operation == "Ok", arguments[0])
        operations = {
            "!": lambda a: not a,
            "-": lambda a: -a,  # type: ignore[operator]
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "+": lambda a, b: a + b,  # type: ignore[operator]
            "-binary": lambda a, b: a - b,  # type: ignore[operator]
            "*": lambda a, b: a * b,  # type: ignore[operator]
            "/": lambda a, b: a / b,  # type: ignore[operator]
            "&": lambda a, b: bool(a) and bool(b),
            "|": lambda a, b: bool(a) or bool(b),
            "<": lambda a, b: a < b,  # type: ignore[operator]
            "<=": lambda a, b: a <= b,  # type: ignore[operator]
            ">": lambda a, b: a > b,  # type: ignore[operator]
            ">=": lambda a, b: a >= b,  # type: ignore[operator]
        }
        operation = value.operation
        if operation == "-" and len(arguments) == 2:
            operation = "-binary"
        function = operations.get(operation)
        if function is None:
            return _UNKNOWN_CONCRETE
        try:
            return function(*arguments)
        except Exception:
            return _UNKNOWN_CONCRETE
    if isinstance(value, PhiValue):
        concrete_values = {
            repr(_concrete_from_abstract(item, inputs))
            for item in value.values
        }
        if len(concrete_values) == 1:
            return _concrete_from_abstract(value.values[0], inputs)
    return _UNKNOWN_CONCRETE


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

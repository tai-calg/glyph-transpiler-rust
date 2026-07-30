from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from .._transition_branch_semantics import simplify_expr, substitute_expr
from ..artifacts import CompilationModel
from ..compiler import (
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    FunctionDecl,
    NameExpr,
    Param,
    ProductDecl,
    SumDecl,
    UnaryExpr,
)
from .exactness import (
    Approximation,
    ApproximationCause,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)
from .machine_relation import relation_by_transition_function


FUNCTION_SUMMARY_VERSION = 1


@dataclass(frozen=True)
class SummaryAlternative:
    condition: Expr
    value: Expr

    def to_ir(self) -> dict[str, object]:
        return {
            "condition": repr(self.condition),
            "value": repr(self.value),
        }


@dataclass(frozen=True)
class PureFunctionSummary:
    function: str
    parameters: tuple[Param, ...]
    alternatives: tuple[SummaryAlternative, ...]
    recursive_scc: tuple[str, ...]
    iterations: int
    approximation: Approximation

    @property
    def exact_unconditional_value(self) -> Expr | None:
        if not self.approximation.is_exact or len(self.alternatives) != 1:
            return None
        alternative = self.alternatives[0]
        if isinstance(alternative.condition, BoolExpr) and alternative.condition.value:
            return alternative.value
        return None

    def to_ir(self) -> dict[str, object]:
        return {
            "version": FUNCTION_SUMMARY_VERSION,
            "function": self.function,
            "parameters": [parameter.name for parameter in self.parameters],
            "alternatives": [item.to_ir() for item in self.alternatives],
            "recursive_scc": list(self.recursive_scc),
            "iterations": self.iterations,
            "approximation": self.approximation.to_ir(),
        }


@dataclass(frozen=True)
class SummaryApplication:
    function: str
    alternatives: tuple[SummaryAlternative, ...]
    approximation: Approximation

    def to_ir(self) -> dict[str, object]:
        return {
            "function": self.function,
            "alternatives": [item.to_ir() for item in self.alternatives],
            "approximation": self.approximation.to_ir(),
        }


@dataclass(frozen=True)
class FunctionSummarySet:
    summaries: tuple[tuple[str, PureFunctionSummary], ...]
    sccs: tuple[tuple[str, ...], ...]

    @property
    def mapping(self) -> dict[str, PureFunctionSummary]:
        return dict(self.summaries)

    def to_ir(self) -> dict[str, object]:
        return {
            "version": FUNCTION_SUMMARY_VERSION,
            "sccs": [list(component) for component in self.sccs],
            "summaries": {
                name: summary.to_ir() for name, summary in self.summaries
            },
        }


def build_pure_function_summaries(
    model: CompilationModel,
    *,
    max_iterations: int = 16,
) -> FunctionSummarySet:
    if max_iterations <= 0:
        raise ValueError("summary fixpoint iteration budget must be positive")

    transition_functions = frozenset(relation_by_transition_function(model))
    declarations = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, FunctionDecl)
        and not declaration.name.startswith("__glyph_block_")
        and declaration.name not in transition_functions
    }
    graph = {
        name: frozenset(_called_functions(declaration) & declarations.keys())
        for name, declaration in declarations.items()
    }
    sccs = _strongly_connected_components(graph)
    component_by_name = {
        name: component for component in sccs for name in component
    }
    products = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, ProductDecl)
    }
    constants = frozenset(
        variant.name
        for declaration in model.program.declarations
        if isinstance(declaration, SumDecl)
        for variant in declaration.variants
    )

    summaries: dict[str, PureFunctionSummary] = {
        name: PureFunctionSummary(
            name,
            declaration.params,
            _declaration_alternatives(declaration),
            component_by_name[name] if _is_recursive(name, graph, component_by_name[name]) else (),
            0,
            _exact_summary(name),
        )
        for name, declaration in declarations.items()
    }

    stable = False
    iterations = 0
    while not stable and iterations < max_iterations:
        iterations += 1
        stable = True
        next_summaries: dict[str, PureFunctionSummary] = {}
        for name, summary in summaries.items():
            component = frozenset(component_by_name[name])
            expanded = tuple(
                SummaryAlternative(
                    simplify_expr(
                        _inline_exact_calls(
                            alternative.condition,
                            summaries,
                            blocked=component,
                        ),
                        products=products,
                        constants=constants,
                    ),
                    simplify_expr(
                        _inline_exact_calls(
                            alternative.value,
                            summaries,
                            blocked=component,
                        ),
                        products=products,
                        constants=constants,
                    ),
                )
                for alternative in summary.alternatives
            )
            candidate = replace(summary, alternatives=expanded, iterations=iterations)
            next_summaries[name] = candidate
            if candidate.alternatives != summary.alternatives:
                stable = False
        summaries = next_summaries

    for name, summary in tuple(summaries.items()):
        recursive_calls = frozenset(summary.recursive_scc)
        unresolved_recursive = any(
            _expression_calls(item.condition) & recursive_calls
            or _expression_calls(item.value) & recursive_calls
            for item in summary.alternatives
        )
        if unresolved_recursive:
            summaries[name] = replace(
                summary,
                approximation=Approximation.unknown(
                    ApproximationCause.RECURSIVE_SUMMARY_LIMIT
                ),
            )
        elif not stable and graph.get(name):
            summaries[name] = replace(
                summary,
                approximation=summary.approximation.degrade(
                    ApproximationCause.RECURSIVE_SUMMARY_LIMIT,
                    unknown=True,
                ),
            )

    return FunctionSummarySet(
        tuple(sorted(summaries.items(), key=lambda item: item[0])),
        tuple(sccs),
    )


def instantiate_pure_summary(
    summary: PureFunctionSummary,
    arguments: Sequence[Expr],
    *,
    caller_condition: Expr = BoolExpr(True),
) -> SummaryApplication:
    if len(arguments) != len(summary.parameters):
        return SummaryApplication(
            summary.function,
            (),
            Approximation.unknown("pure-summary-arity-mismatch"),
        )
    substitution = {
        parameter.name: argument
        for parameter, argument in zip(
            summary.parameters,
            arguments,
            strict=True,
        )
    }
    return SummaryApplication(
        summary.function,
        tuple(
            SummaryAlternative(
                _and(
                    caller_condition,
                    substitute_expr(alternative.condition, substitution),
                ),
                substitute_expr(alternative.value, substitution),
            )
            for alternative in summary.alternatives
        ),
        summary.approximation,
    )


def inline_exact_pure_calls(
    expression: Expr,
    summaries: Mapping[str, PureFunctionSummary],
    *,
    max_depth: int = 32,
) -> Expr:
    result = expression
    for _ in range(max_depth):
        expanded = _inline_exact_calls(result, summaries, blocked=frozenset())
        if expanded == result:
            return result
        result = expanded
    return result


def _declaration_alternatives(
    declaration: FunctionDecl,
) -> tuple[SummaryAlternative, ...]:
    if declaration.expression is not None:
        return (SummaryAlternative(BoolExpr(True), declaration.expression),)
    remaining: Expr = BoolExpr(True)
    alternatives: list[SummaryAlternative] = []
    for clause in declaration.guards:
        if clause.condition is None:
            alternatives.append(SummaryAlternative(remaining, clause.value))
            remaining = BoolExpr(False)
            break
        alternatives.append(
            SummaryAlternative(_and(remaining, clause.condition), clause.value)
        )
        remaining = _and(remaining, UnaryExpr("!", clause.condition))
    return tuple(alternatives)


def _inline_exact_calls(
    expression: Expr,
    summaries: Mapping[str, PureFunctionSummary],
    *,
    blocked: frozenset[str],
) -> Expr:
    if isinstance(expression, CallExpr):
        callee = _inline_exact_calls(expression.callee, summaries, blocked=blocked)
        arguments = tuple(
            _inline_exact_calls(argument, summaries, blocked=blocked)
            for argument in expression.args
        )
        call = CallExpr(callee, arguments)
        if not isinstance(callee, NameExpr) or callee.name in blocked:
            return call
        summary = summaries.get(callee.name)
        if summary is None:
            return call
        value = summary.exact_unconditional_value
        if value is None or len(arguments) != len(summary.parameters):
            return call
        substitution = {
            parameter.name: argument
            for parameter, argument in zip(
                summary.parameters,
                arguments,
                strict=True,
            )
        }
        return substitute_expr(value, substitution)
    if not isinstance(expression, Expr):
        return expression
    values: dict[str, object] = {}
    changed = False
    for name, value in vars(expression).items() if hasattr(expression, "__dict__") else ():
        if isinstance(value, Expr):
            next_value = _inline_exact_calls(value, summaries, blocked=blocked)
        elif isinstance(value, tuple):
            next_value = tuple(
                _inline_exact_calls(item, summaries, blocked=blocked)
                if isinstance(item, Expr)
                else item
                for item in value
            )
        else:
            next_value = value
        values[name] = next_value
        changed = changed or next_value != value
    if not changed:
        return expression
    return type(expression)(**values)


def _called_functions(declaration: FunctionDecl) -> frozenset[str]:
    expressions = [
        *(clause.condition for clause in declaration.guards if clause.condition is not None),
        *(clause.value for clause in declaration.guards),
    ]
    if declaration.expression is not None:
        expressions.append(declaration.expression)
    return frozenset(
        name for expression in expressions for name in _expression_calls(expression)
    )


def _expression_calls(expression: Expr) -> frozenset[str]:
    calls: set[str] = set()

    def visit(value: object) -> None:
        if not isinstance(value, Expr):
            return
        if isinstance(value, CallExpr) and isinstance(value.callee, NameExpr):
            calls.add(value.callee.name)
        for child in vars(value).values() if hasattr(value, "__dict__") else ():
            if isinstance(child, Expr):
                visit(child)
            elif isinstance(child, tuple):
                for item in child:
                    visit(item)

    visit(expression)
    return frozenset(calls)


def _strongly_connected_components(
    graph: Mapping[str, frozenset[str]],
) -> tuple[tuple[str, ...], ...]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in sorted(graph.get(node, frozenset())):
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            item = stack.pop()
            on_stack.remove(item)
            component.append(item)
            if item == node:
                break
        components.append(tuple(sorted(component)))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return tuple(components)


def _is_recursive(
    name: str,
    graph: Mapping[str, frozenset[str]],
    component: tuple[str, ...],
) -> bool:
    return len(component) > 1 or name in graph.get(name, frozenset())


def _exact_summary(name: str) -> Approximation:
    return Approximation.exact(
        ExactnessProof(
            ExactnessProofKind.STRUCTURAL_IDENTITY,
            ExactnessProofScope.FUNCTION_SUMMARY,
            f"ordered pure-function summary for {name}",
        )
    )


def _and(left: Expr, right: Expr) -> Expr:
    if isinstance(left, BoolExpr):
        return right if left.value else left
    if isinstance(right, BoolExpr):
        return left if right.value else right
    return BinaryExpr("&", left, right)

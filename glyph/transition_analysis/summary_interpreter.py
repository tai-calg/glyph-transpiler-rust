from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from ..artifacts import CompilationModel
from ..compiler import (
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    FieldExpr,
    NameExpr,
    NumberExpr,
    TryExpr,
    UnaryExpr,
)
from .abstract_solver import AbstractInterpreter
from .abstract_state import (
    AbstractAnalysisResult,
    AbstractTransitionEvent,
    AnalysisBudget,
    GuardedAlternative,
)
from .abstract_value import (
    AbstractValue,
    ApplicationValue,
    ConstantValue,
    ConstructorValue,
    FieldValue,
    ParameterValue,
    PhiValue,
    TopValue,
    value_from_expr,
)
from .effect_summary import (
    AbstractEffectEvent,
    EffectSummary,
    apply_effect_summary,
)
from .exactness import Approximation
from .function_summary import (
    FunctionSummarySet,
    build_pure_function_summaries,
    inline_exact_pure_calls,
)
from .preimage import PreimageStatus, compute_transition_call_preimage
from .teir import TransitionCall


@dataclass(frozen=True)
class ContextualEffectSummaryRegistry:
    """Select verified Effect summaries by System entry context.

    An entry-specific summary shadows the operation default. Missing entries do
    not inherit summaries from unrelated callers; they fall back to the explicit
    default or the AbstractInterpreter's conservative unknown Effect summary.
    """

    defaults: tuple[tuple[str, EffectSummary], ...] = ()
    by_entry: tuple[tuple[str, tuple[tuple[str, EffectSummary], ...]], ...] = ()

    def resolve(self, entry: str) -> dict[str, EffectSummary]:
        result = dict(self.defaults)
        for candidate, summaries in self.by_entry:
            if candidate == entry:
                result.update(dict(summaries))
                break
        return result


@dataclass(frozen=True)
class _NestedEffectEvaluation:
    expression: Expr
    store: object
    events: tuple[AbstractEffectEvent, ...]
    approximation: Approximation
    issues: tuple[str, ...] = ()


class SummaryAwareAbstractInterpreter(AbstractInterpreter):
    """Abstract interpreter with context-sensitive pure and Effect summaries.

    A Machine result may contain a contracted Effect call inside a constructor,
    for example ``State(Stopped, write_motor(command))``. The base interpreter
    preserves that expression but cannot add the nested call to EffectTrace. This
    subclass evaluates deterministic reviewed summaries in source evaluation order,
    updates the abstract store, records the Effect event and rewrites the call to its
    reviewed return expression. The rewrite prevents a later field projection from
    replaying the same Effect.
    """

    def __init__(
        self,
        model: CompilationModel,
        *,
        effect_summaries: Mapping[str, EffectSummary] | None = None,
        contextual_effect_summaries: ContextualEffectSummaryRegistry | None = None,
        function_summaries: FunctionSummarySet | None = None,
        summary_iterations: int = 16,
        budget: AnalysisBudget = AnalysisBudget(),
    ) -> None:
        super().__init__(
            model,
            effect_summaries=effect_summaries,
            budget=budget,
        )
        self.function_summary_set = function_summaries or build_pure_function_summaries(
            model,
            max_iterations=summary_iterations,
        )
        self.function_summaries = self.function_summary_set.mapping
        self.contextual_effect_summaries = contextual_effect_summaries
        self._default_effect_summaries = dict(self.effect_summaries)

    def analyze(self, function_name: str) -> AbstractAnalysisResult:
        selected = dict(self._default_effect_summaries)
        if self.contextual_effect_summaries is not None:
            selected.update(self.contextual_effect_summaries.resolve(function_name))
        previous = self.effect_summaries
        self.effect_summaries = selected
        try:
            return super().analyze(function_name)
        finally:
            self.effect_summaries = previous

    def _symbolic(
        self,
        expression: Expr,
        alternative: GuardedAlternative,
    ) -> Expr:
        symbolic = super()._symbolic(expression, alternative)
        expanded = inline_exact_pure_calls(symbolic, self.function_summaries)
        return super()._symbolic(expanded, alternative)

    def _transfer_transition(
        self,
        instruction: TransitionCall,
        alternative: GuardedAlternative,
    ) -> tuple[list[GuardedAlternative], list[GuardedAlternative]]:
        symbolic_arguments = tuple(
            self._symbolic(argument, alternative)
            for argument in instruction.arguments
        )
        abstract_arguments = tuple(
            self._evaluate_expression(argument, alternative)[1]
            for argument in instruction.arguments
        )
        preimage = compute_transition_call_preimage(
            self.model,
            instruction.machine,
            symbolic_arguments,
            caller_condition=alternative.path_condition,
        )
        if preimage is None or not preimage.edges:
            unknown = alternative.bind(
                instruction.target,
                TopValue("transition-preimage-unavailable"),
                NameExpr(instruction.target),
            ).degrade(
                "transition-preimage-unavailable",
                unknown=True,
                transition_trace_top=True,
            )
            return [unknown], []

        running: list[GuardedAlternative] = []
        terminals: list[GuardedAlternative] = []
        for edge in preimage.edges:
            if edge.status is PreimageStatus.PROVEN_FALSE:
                continue

            nested = self._evaluate_nested_effects(
                edge.result_expression,
                alternative,
            )
            approximation = Approximation.combine(
                (
                    alternative.approximation,
                    edge.approximation,
                    nested.approximation,
                )
            )
            symbolic_result = nested.expression
            result_value = value_from_expr(
                symbolic_result,
                alternative.environment_map,
                context=instruction.function,
                product_fields=self.product_fields,
                constants=self.constants,
            )
            if isinstance(result_value, TopValue):
                approximation = approximation.degrade(result_value.reason, unknown=True)

            base = replace(
                alternative,
                path_condition=edge.condition,
                store=nested.store,  # type: ignore[arg-type]
                effect_trace=(*alternative.effect_trace, *nested.events),
                effect_trace_top=(
                    alternative.effect_trace_top or bool(nested.issues)
                ),
                unknown_reasons=tuple(
                    sorted(set((*alternative.unknown_reasons, *nested.issues)))
                ),
                approximation=approximation,
                transition_trace=(
                    *alternative.transition_trace,
                    AbstractTransitionEvent(
                        instruction.machine,
                        instruction.function,
                        edge.edge_id,
                        abstract_arguments,
                        result_value,
                    ),
                ),
            )
            if not instruction.propagate_failure:
                running.append(
                    base.bind(
                        instruction.target,
                        result_value,
                        symbolic_result,
                        approximation=approximation,
                    )
                )
                continue

            result_kind, payload = _result_expression(symbolic_result)
            if result_kind == "ok" and payload is not None:
                payload_value = value_from_expr(
                    payload,
                    alternative.environment_map,
                    context=instruction.function,
                    product_fields=self.product_fields,
                    constants=self.constants,
                )
                running.append(
                    base.bind(
                        instruction.target,
                        payload_value,
                        payload,
                        approximation=approximation,
                    )
                )
                continue
            if result_kind == "err":
                terminals.append(
                    replace(
                        base,
                        completion=frozenset({"propagated-failure"}),
                        return_value=(
                            None
                            if payload is None
                            else value_from_expr(
                                payload,
                                alternative.environment_map,
                                context=instruction.function,
                                product_fields=self.product_fields,
                                constants=self.constants,
                            )
                        ),
                    )
                )
                continue

            uncertain = base.degrade(
                "transition-result-kind-unknown",
                unknown=True,
            )
            running.append(
                uncertain.bind(
                    instruction.target,
                    TopValue("transition-success-value-unknown"),
                    NameExpr(instruction.target),
                )
            )
            terminals.append(
                replace(
                    uncertain,
                    completion=frozenset({"propagated-failure"}),
                    return_value=TopValue("transition-failure-value-unknown"),
                )
            )
        return running, terminals

    def _evaluate_nested_effects(
        self,
        expression: Expr,
        alternative: GuardedAlternative,
    ) -> _NestedEffectEvaluation:
        return self._rewrite_expression(
            expression,
            alternative,
            alternative.store,
            (),
            alternative.approximation,
            (),
        )

    def _rewrite_expression(
        self,
        expression: Expr,
        alternative: GuardedAlternative,
        store: object,
        events: tuple[AbstractEffectEvent, ...],
        approximation: Approximation,
        issues: tuple[str, ...],
    ) -> _NestedEffectEvaluation:
        if isinstance(expression, CallExpr):
            rewritten_arguments: list[Expr] = []
            current_store = store
            current_events = events
            current_approximation = approximation
            current_issues = issues
            for argument in expression.args:
                item = self._rewrite_expression(
                    argument,
                    alternative,
                    current_store,
                    current_events,
                    current_approximation,
                    current_issues,
                )
                rewritten_arguments.append(item.expression)
                current_store = item.store
                current_events = item.events
                current_approximation = item.approximation
                current_issues = item.issues

            rewritten = CallExpr(expression.callee, tuple(rewritten_arguments))
            if not isinstance(expression.callee, NameExpr):
                return _NestedEffectEvaluation(
                    rewritten,
                    current_store,
                    current_events,
                    current_approximation,
                    current_issues,
                )

            operation = expression.callee.name
            if operation not in self.effects:
                return _NestedEffectEvaluation(
                    rewritten,
                    current_store,
                    current_events,
                    current_approximation,
                    current_issues,
                )

            summary = self.effect_summaries.get(operation)
            if summary is None:
                return self._nested_effect_unknown(
                    rewritten,
                    current_store,
                    current_events,
                    current_approximation,
                    current_issues,
                    f"nested-effect-contract-missing:{operation}",
                )

            abstract_arguments = tuple(
                value_from_expr(
                    argument,
                    alternative.environment_map,
                    context=operation,
                    product_fields=self.product_fields,
                    constants=self.constants,
                )
                for argument in rewritten_arguments
            )
            application = apply_effect_summary(
                summary,
                abstract_arguments,
                current_store,  # type: ignore[arg-type]
            )
            combined = Approximation.combine(
                (current_approximation, application.approximation)
            )
            if tuple(application.completions) != ("normal",):
                return self._nested_effect_unknown(
                    rewritten,
                    application.store,
                    (*current_events, application.event),
                    combined,
                    current_issues,
                    f"nested-effect-completion-not-deterministic:{operation}",
                )

            replacement = _abstract_value_to_expr(application.result)
            if replacement is None:
                return self._nested_effect_unknown(
                    rewritten,
                    application.store,
                    (*current_events, application.event),
                    combined,
                    current_issues,
                    f"nested-effect-return-not-expressible:{operation}",
                )
            return _NestedEffectEvaluation(
                replacement,
                application.store,
                (*current_events, application.event),
                combined,
                current_issues,
            )

        if isinstance(expression, FieldExpr):
            base = self._rewrite_expression(
                expression.base,
                alternative,
                store,
                events,
                approximation,
                issues,
            )
            return _NestedEffectEvaluation(
                FieldExpr(base.expression, expression.field),
                base.store,
                base.events,
                base.approximation,
                base.issues,
            )
        if isinstance(expression, UnaryExpr):
            value = self._rewrite_expression(
                expression.expr,
                alternative,
                store,
                events,
                approximation,
                issues,
            )
            return _NestedEffectEvaluation(
                UnaryExpr(expression.op, value.expression),
                value.store,
                value.events,
                value.approximation,
                value.issues,
            )
        if isinstance(expression, BinaryExpr):
            left = self._rewrite_expression(
                expression.left,
                alternative,
                store,
                events,
                approximation,
                issues,
            )
            right = self._rewrite_expression(
                expression.right,
                alternative,
                left.store,
                left.events,
                left.approximation,
                left.issues,
            )
            return _NestedEffectEvaluation(
                BinaryExpr(expression.op, left.expression, right.expression),
                right.store,
                right.events,
                right.approximation,
                right.issues,
            )
        if isinstance(expression, TryExpr):
            value = self._rewrite_expression(
                expression.expr,
                alternative,
                store,
                events,
                approximation,
                issues,
            )
            return _NestedEffectEvaluation(
                TryExpr(value.expression),
                value.store,
                value.events,
                value.approximation,
                value.issues,
            )
        return _NestedEffectEvaluation(
            expression,
            store,
            events,
            approximation,
            issues,
        )

    @staticmethod
    def _nested_effect_unknown(
        expression: Expr,
        store: object,
        events: tuple[AbstractEffectEvent, ...],
        approximation: Approximation,
        issues: tuple[str, ...],
        reason: str,
    ) -> _NestedEffectEvaluation:
        return _NestedEffectEvaluation(
            expression,
            store,
            events,
            approximation.degrade(reason, unknown=True),
            tuple(sorted(set((*issues, reason)))),
        )


def _abstract_value_to_expr(value: AbstractValue) -> Expr | None:
    if isinstance(value, ParameterValue):
        return NameExpr(value.name)
    if isinstance(value, ConstantValue):
        if isinstance(value.value, bool):
            return BoolExpr(value.value)
        if isinstance(value.value, (int, float)):
            return NumberExpr(str(value.value))
        if isinstance(value.value, str):
            return NameExpr(value.value)
        return None
    if isinstance(value, FieldValue):
        base = _abstract_value_to_expr(value.base)
        return None if base is None else FieldExpr(base, value.field)
    if isinstance(value, ConstructorValue):
        arguments = tuple(_abstract_value_to_expr(item) for item in value.arguments)
        if any(item is None for item in arguments):
            return None
        return CallExpr(
            NameExpr(value.type_name),
            tuple(item for item in arguments if item is not None),
        )
    if isinstance(value, ApplicationValue):
        arguments = tuple(_abstract_value_to_expr(item) for item in value.arguments)
        if any(item is None for item in arguments):
            return None
        return CallExpr(
            NameExpr(value.operation),
            tuple(item for item in arguments if item is not None),
        )
    if isinstance(value, (PhiValue, TopValue)):
        return None
    return None


def _result_expression(expression: Expr) -> tuple[str, Expr | None]:
    if (
        isinstance(expression, CallExpr)
        and isinstance(expression.callee, NameExpr)
        and expression.callee.name in {"Ok", "Err"}
        and len(expression.args) == 1
    ):
        return expression.callee.name.lower(), expression.args[0]
    return "unknown", None

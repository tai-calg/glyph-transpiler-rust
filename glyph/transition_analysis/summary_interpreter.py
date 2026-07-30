from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..artifacts import CompilationModel
from ..compiler import Expr
from .abstract_solver import AbstractInterpreter
from .abstract_state import AbstractAnalysisResult, AnalysisBudget, GuardedAlternative
from .effect_summary import EffectSummary
from .function_summary import (
    FunctionSummarySet,
    build_pure_function_summaries,
    inline_exact_pure_calls,
)


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


class SummaryAwareAbstractInterpreter(AbstractInterpreter):
    """Abstract interpreter with context-sensitive pure and Effect summaries."""

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

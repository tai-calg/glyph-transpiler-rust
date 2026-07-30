from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.compiler import BoolExpr, NameExpr
from glyph.transition_analysis.abstract_value import TopValue
from glyph.transition_analysis.effect_summary import identity_effect_summary
from glyph.transition_analysis.exactness import (
    Approximation,
    ApproximationKind,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)
from glyph.transition_analysis.function_summary import (
    build_pure_function_summaries,
    instantiate_pure_summary,
)
from glyph.transition_analysis.summary_interpreter import (
    ContextualEffectSummaryRegistry,
    SummaryAwareAbstractInterpreter,
)


PURE_SOURCE = """>identity(x:B):B=x
>negate(x:B):B=!identity(x)

>choose(x:B):B
  x >> True
  _ >> False

>recur(x:B):B=recur(x)

>control(x:B):B=negate(x)
"""


EFFECT_SOURCE = """!observe(value:B):B

>entry_a(value:B):B
  observed := observe(value)
  observed

>entry_b(value:B):B
  observed := observe(value)
  observed
"""


def exact_effect() -> Approximation:
    return Approximation.exact(
        ExactnessProof(
            ExactnessProofKind.STRUCTURAL_IDENTITY,
            ExactnessProofScope.EFFECT_TRACE,
            "verified entry-specific identity Effect",
        )
    )


class PureFunctionSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = CompilationPipeline().compile_text(
            PURE_SOURCE,
            source_name="pure-summary.glyph",
        ).model
        cls.summaries = build_pure_function_summaries(cls.model)

    def test_non_recursive_helper_is_inlined_to_fixpoint(self) -> None:
        summary = self.summaries.mapping["negate"]
        self.assertTrue(summary.approximation.is_exact)
        self.assertNotIn("identity", repr(summary.alternatives[0].value))

    def test_guarded_summary_preserves_ordered_choices_after_instantiation(self) -> None:
        summary = self.summaries.mapping["choose"]
        application = instantiate_pure_summary(
            summary,
            (NameExpr("input"),),
            caller_condition=BoolExpr(True),
        )
        self.assertEqual(len(application.alternatives), 2)
        self.assertIn("input", repr(application.alternatives[0].condition))
        self.assertIn("UnaryExpr", repr(application.alternatives[1].condition))

    def test_recursive_scc_is_unknown_instead_of_false_exact(self) -> None:
        summary = self.summaries.mapping["recur"]
        self.assertEqual(summary.recursive_scc, ("recur",))
        self.assertEqual(summary.approximation.kind, ApproximationKind.UNKNOWN)
        self.assertIn("recursive-summary-limit", summary.approximation.causes)

    def test_summary_aware_interpreter_resolves_exact_unguarded_helper(self) -> None:
        result = SummaryAwareAbstractInterpreter(self.model).analyze("control")
        self.assertTrue(result.approximation.is_exact)
        self.assertEqual(len(result.completed), 1)
        self.assertNotIsInstance(result.completed[0].return_value, TopValue)
        self.assertNotIn("unmodeled-call", result.unknown_reasons)


class ContextualEffectSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = CompilationPipeline().compile_text(
            EFFECT_SOURCE,
            source_name="contextual-effect-summary.glyph",
        ).model
        summary = identity_effect_summary(
            "observe",
            "value",
            approximation=exact_effect(),
        )
        cls.registry = ContextualEffectSummaryRegistry(
            by_entry=(("entry_a", (("observe", summary),)),),
        )

    def test_entry_specific_effect_summary_does_not_leak_to_other_entry(self) -> None:
        analyzer = SummaryAwareAbstractInterpreter(
            self.model,
            contextual_effect_summaries=self.registry,
        )
        exact = analyzer.analyze("entry_a")
        unknown = analyzer.analyze("entry_b")
        self.assertTrue(exact.approximation.is_exact)
        self.assertEqual(unknown.approximation.kind, ApproximationKind.UNKNOWN)
        self.assertIn("unknown-effect-result", unknown.approximation.causes)


if __name__ == "__main__":
    unittest.main()

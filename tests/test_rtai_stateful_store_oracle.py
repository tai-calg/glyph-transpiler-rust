from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.transition_analysis.abstract_store import AbstractLocation
from glyph.transition_analysis.abstract_value import ParameterValue
from glyph.transition_analysis.effect_summary import EffectSummary
from glyph.transition_analysis.exactness import (
    Approximation,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)
from glyph.transition_analysis.oracle import compare_bounded_teir_and_abstract
from glyph.transition_analysis.stateful_concrete import (
    StatefulConcreteInterpreter,
    StatefulEffectResult,
)


SOURCE = """!write_flag(value:B):B

>control(value:B):B
  result := write_flag(value)
  result
"""


def exact_effect() -> Approximation:
    return Approximation.exact(
        ExactnessProof(
            ExactnessProofKind.STRUCTURAL_IDENTITY,
            ExactnessProofScope.EFFECT_TRACE,
            "verified stateful flag Effect",
        )
    )


class StatefulStoreOracleTests(unittest.TestCase):
    def test_concrete_final_store_is_included_in_abstract_store(self) -> None:
        model = CompilationPipeline().compile_text(
            SOURCE,
            source_name="stateful-store-oracle.glyph",
        ).model
        location = AbstractLocation("external", "flag")
        summary = EffectSummary(
            operation="write_flag",
            parameters=("value",),
            return_value=ParameterValue("write_flag", "value"),
            reads=(),
            writes=(location,),
            store_updates=(
                (location, ParameterValue("write_flag", "value")),
            ),
            completions=("normal",),
            approximation=exact_effect(),
        )
        report = compare_bounded_teir_and_abstract(
            model,
            "control",
            effect_handlers={
                "write_flag": lambda arguments: StatefulEffectResult(
                    arguments[0],
                    ((("external", "flag"), arguments[0]),),
                )
            },
            effect_summaries={"write_flag": summary},
            concrete_interpreter_type=StatefulConcreteInterpreter,
        )
        self.assertEqual(len(report.cases), 2)
        self.assertTrue(report.sound_for_bounded_domain, report.uncovered)
        self.assertTrue(all(case.store_covered for case in report.cases))
        self.assertEqual(
            {
                case.concrete.final_store[0][1]
                for case in report.cases
            },
            {False, True},
        )


if __name__ == "__main__":
    unittest.main()

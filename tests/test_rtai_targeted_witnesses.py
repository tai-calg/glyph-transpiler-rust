from __future__ import annotations

import unittest

from glyph.compilation import CompilationPipeline
from glyph.transition_analysis import (
    ConstructorValue,
    TargetedWitnessCase,
    TargetedWitnessRegistry,
    VariantValue,
    VerifiedEffectContractRegistry,
    audit_effect_contract_coverage,
    generate_bounded_system_witnesses,
    read_only_identity_contract,
)


FIELDS = ",".join(f"b{index}:B" for index in range(13))
SOURCE = f"""system LargeControl
  entry control

  in state:State
  in input:Input
  out state_out:State

  state -> control
  input -> control
  control -> state_out
  control -> actuator

machine Large(state:State,input:Input)
  select=state.mode
  init=State(Idle)
  next=step(state,input)
  success=Active
  failure=Idle

+Mode=Idle|Active
*State(mode:Mode)
*Input({FIELDS})

!actuator(state:State):State

>step(state:State,input:Input):State
  input.b0 >> State(Active)
  _ >> State(Idle)

>apply(state:State):State=actuator(state)

>control(state:State,input:Input):State
  next := step(state,input)
  observed := apply(next)
  observed
"""


def state(mode: str) -> ConstructorValue:
    return ConstructorValue("State", (("mode", VariantValue(mode)),))


def input_value(first: bool) -> ConstructorValue:
    return ConstructorValue(
        "Input",
        tuple((f"b{index}", first if index == 0 else False) for index in range(13)),
    )


class TargetedWitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        output = CompilationPipeline().compile_text(
            SOURCE,
            source_name="targeted-witnesses.glyph",
        )
        cls.model = output.model
        cls.contracts = VerifiedEffectContractRegistry(
            defaults=(
                (
                    "actuator",
                    read_only_identity_contract(
                        "actuator",
                        "state",
                        source="tests: reviewed identity actuator",
                    ),
                ),
            )
        )
        cls.targets = TargetedWitnessRegistry(
            (
                TargetedWitnessCase(
                    "control",
                    (state("Idle"), input_value(False)),
                    source="tests: idle edge representative",
                    label="idle",
                ),
                TargetedWitnessCase(
                    "control",
                    (state("Idle"), input_value(True)),
                    source="tests: active edge representative",
                    label="active",
                ),
            )
        )

    def test_targeted_cases_replace_oversized_finite_enumeration(self) -> None:
        report = generate_bounded_system_witnesses(
            self.model,
            ("control",),
            self.contracts,
            max_cases_per_entry=64,
            targeted_witnesses=self.targets,
        )
        self.assertTrue(report.complete, report.issues)
        self.assertFalse(report.exhaustive)
        self.assertEqual(report.attempted_case_count, 2)
        self.assertEqual(report.completed_case_count, 2)
        self.assertEqual(report.entry_coverage[0].strategy, "targeted-existence")
        self.assertFalse(report.entry_coverage[0].exhaustive)
        self.assertEqual(len({item.edge_id for item in report.witnesses}), 2)
        self.assertTrue(
            all(item.generation_strategy == "targeted-existence" for item in report.witnesses)
        )

    def test_large_domain_without_targets_fails_closed(self) -> None:
        report = generate_bounded_system_witnesses(
            self.model,
            ("control",),
            self.contracts,
            max_cases_per_entry=64,
        )
        self.assertFalse(report.complete)
        self.assertEqual(report.witnesses, ())
        self.assertEqual(report.issues[0].code, "finite-domain-unavailable")

    def test_effect_contract_audit_follows_helper_calls(self) -> None:
        report = audit_effect_contract_coverage(
            self.model,
            ("control",),
            self.contracts,
        )
        self.assertTrue(report.complete)
        entry = report.entries[0]
        self.assertIn("apply", entry.reachable_functions)
        self.assertEqual(entry.required_operations, ("actuator",))
        self.assertEqual(entry.covered_operations, ("actuator",))
        self.assertEqual(entry.missing_operations, ())

    def test_effect_contract_audit_lists_all_missing_boundaries(self) -> None:
        report = audit_effect_contract_coverage(
            self.model,
            ("control",),
            VerifiedEffectContractRegistry(),
        )
        self.assertFalse(report.complete)
        self.assertEqual(report.missing_operations, ("actuator",))
        self.assertEqual(report.entries[0].missing_operations, ("actuator",))


if __name__ == "__main__":
    unittest.main()

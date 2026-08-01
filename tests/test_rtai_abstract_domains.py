from __future__ import annotations

import unittest

from glyph.compiler import CallExpr, FieldExpr, NameExpr
from glyph.transition_analysis.abstract_store import (
    AbstractAddress,
    AbstractLocation,
    AbstractStore,
)
from glyph.transition_analysis.abstract_value import (
    ConstantValue,
    ConstructorValue,
    FieldValue,
    ParameterValue,
    PhiValue,
    TopValue,
    normalize_value,
    value_from_expr,
)
from glyph.transition_analysis.effect_summary import (
    apply_effect_summary,
    identity_effect_summary,
    unknown_effect_summary,
)
from glyph.transition_analysis.exactness import (
    Approximation,
    ApproximationKind,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)


def exact_structural(detail: str) -> Approximation:
    return Approximation.exact(
        ExactnessProof(
            ExactnessProofKind.STRUCTURAL_IDENTITY,
            ExactnessProofScope.STRUCTURAL,
            detail,
        )
    )


class AbstractValueTests(unittest.TestCase):
    def test_constructor_order_is_preserved(self) -> None:
        environment = {
            "input": ParameterValue("control", "input"),
        }
        normal = value_from_expr(
            CallExpr(
                NameExpr("Input"),
                (
                    FieldExpr(NameExpr("input"), "open_request"),
                    FieldExpr(NameExpr("input"), "authorized"),
                ),
            ),
            environment,
            context="control",
            product_fields={"Input": ("open_request", "authorized")},
        )
        swapped = value_from_expr(
            CallExpr(
                NameExpr("Input"),
                (
                    FieldExpr(NameExpr("input"), "authorized"),
                    FieldExpr(NameExpr("input"), "open_request"),
                ),
            ),
            environment,
            context="control",
            product_fields={"Input": ("open_request", "authorized")},
        )
        self.assertNotEqual(normal, swapped)

    def test_field_projection_of_constructor_is_normalized(self) -> None:
        value = ConstructorValue(
            "Pair",
            ("left", "right"),
            (ConstantValue(1), ConstantValue(2)),
        )
        self.assertEqual(
            normalize_value(FieldValue(value, "right")),
            ConstantValue(2),
        )


class AbstractStoreTests(unittest.TestCase):
    def test_strong_update_requires_proven_singleton(self) -> None:
        location = AbstractLocation("resource", "door")
        store = AbstractStore.empty().write(
            AbstractAddress(frozenset({location}), singleton_proven=True),
            ConstantValue("Closed"),
        )
        updated = store.write(
            AbstractAddress(frozenset({location}), singleton_proven=True),
            ConstantValue("Open"),
        )
        self.assertEqual(updated.read(AbstractAddress(frozenset({location}))), ConstantValue("Open"))
        self.assertTrue(updated.approximation.is_exact)

    def test_weak_update_keeps_old_and_new_values(self) -> None:
        left = AbstractLocation("resource", "left")
        right = AbstractLocation("resource", "right")
        store = AbstractStore.empty()
        store = store.write(
            AbstractAddress(frozenset({left}), singleton_proven=True),
            ConstantValue(0),
        )
        store = store.write(
            AbstractAddress(frozenset({right}), singleton_proven=True),
            ConstantValue(0),
        )
        updated = store.write(
            AbstractAddress(frozenset({left, right}), singleton_proven=False),
            ConstantValue(1),
        )
        self.assertEqual(updated.approximation.kind, ApproximationKind.OVER_APPROXIMATE)
        self.assertIsInstance(updated.read(AbstractAddress(frozenset({left}))), PhiValue)
        self.assertIsInstance(updated.read(AbstractAddress(frozenset({right}))), PhiValue)


class EffectSummaryTests(unittest.TestCase):
    def test_unknown_effect_havocs_store_and_keeps_failure_possible(self) -> None:
        location = AbstractLocation("resource", "door")
        store = AbstractStore.empty().write(
            AbstractAddress(frozenset({location}), singleton_proven=True),
            ConstantValue("Closed"),
        )
        summary = unknown_effect_summary("actuator", ("state",))
        application = apply_effect_summary(
            summary,
            (ConstantValue("Open"),),
            store,
        )
        self.assertIsInstance(
            application.store.read(AbstractAddress(frozenset({location}))),
            TopValue,
        )
        self.assertIn("propagated-failure", application.completions)
        self.assertEqual(application.approximation.kind, ApproximationKind.UNKNOWN)

    def test_verified_identity_effect_preserves_argument(self) -> None:
        summary = identity_effect_summary(
            "observe",
            "value",
            approximation=exact_structural("verified identity effect"),
        )
        application = apply_effect_summary(
            summary,
            (ConstantValue(7),),
            AbstractStore.empty(),
        )
        self.assertEqual(application.result, ConstantValue(7))
        self.assertEqual(application.completions, ("normal",))
        self.assertTrue(application.approximation.is_exact)


if __name__ == "__main__":
    unittest.main()

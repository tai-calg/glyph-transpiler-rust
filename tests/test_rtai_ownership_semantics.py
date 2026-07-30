from __future__ import annotations

from dataclasses import replace
import unittest

from glyph.capabilities import (
    CapabilityFunction,
    CapabilityKind,
    CapabilityModel,
    CapabilityOperation,
    CapabilityParam,
    CapabilityType,
    ResourceDecl,
)
from glyph.compilation import CompilationPipeline
from glyph.transition_analysis.exactness import ApproximationKind
from glyph.transition_analysis.ownership_semantics import (
    OwnershipAvailability,
    build_ownership_summaries,
)


SOURCE = ">identity(value:B):B=value\n"


def model_with_capabilities(
    functions: tuple[CapabilityFunction, ...],
    operations: tuple[CapabilityOperation, ...],
):
    model = CompilationPipeline().compile_text(
        SOURCE,
        source_name="ownership-semantics.glyph",
    ).model
    capabilities = CapabilityModel(
        resources=(ResourceDecl("Buffer", (), ("Ready", "Done"), 1),),
        functions=functions,
        operations=operations,
    )
    return replace(
        model,
        capabilities=capabilities,
        expanded=replace(model.expanded, capabilities=capabilities),
    )


def owner_type() -> CapabilityType:
    return CapabilityType(
        CapabilityKind.OWN,
        "Buffer",
        state="Ready",
        raw="own Buffer[Ready]",
    )


class OwnershipSemanticsTests(unittest.TestCase):
    def test_move_transfers_availability_and_emits_write_footprint(self) -> None:
        function = CapabilityFunction(
            "consume",
            ">",
            (CapabilityParam("owner", owner_type(), 1),),
            owner_type(),
            1,
            1,
            1,
        )
        model = model_with_capabilities(
            (function,),
            (CapabilityOperation("consume", "move", "owner", "next", "own", 2),),
        )
        summary = build_ownership_summaries(model)["consume"]
        self.assertTrue(summary.approximation.is_exact)
        final = {item.name: item for item in summary.final}
        self.assertEqual(final["owner"].availability, OwnershipAvailability.MOVED)
        self.assertEqual(final["next"].availability, OwnershipAvailability.AVAILABLE)
        self.assertEqual(len(summary.footprint.moves), 1)
        self.assertEqual(len(summary.footprint.writes), 1)

    def test_move_followed_by_capability_cast_preserves_target_capability(self) -> None:
        function = CapabilityFunction(
            "publish",
            ">",
            (CapabilityParam("owner", owner_type(), 1),),
            CapabilityType(
                CapabilityKind.SHARE,
                "Buffer",
                state="Ready",
                raw="share Buffer[Ready]",
            ),
            1,
            1,
            1,
        )
        model = model_with_capabilities(
            (function,),
            (
                CapabilityOperation("publish", "move", "owner", "shared", None, 2),
                CapabilityOperation(
                    "publish",
                    "capability_cast",
                    "owner",
                    "shared",
                    "share",
                    2,
                ),
            ),
        )
        summary = build_ownership_summaries(model)["publish"]
        self.assertTrue(summary.approximation.is_exact, summary.violations)
        final = {item.name: item for item in summary.final}
        self.assertEqual(final["owner"].availability, OwnershipAvailability.MOVED)
        self.assertEqual(final["shared"].capability, CapabilityKind.SHARE)

    def test_use_after_move_in_capability_ir_is_not_silently_accepted(self) -> None:
        function = CapabilityFunction(
            "invalid",
            ">",
            (CapabilityParam("owner", owner_type(), 1),),
            owner_type(),
            1,
            1,
            1,
        )
        model = model_with_capabilities(
            (function,),
            (
                CapabilityOperation("invalid", "move", "owner", "next", "own", 2),
                CapabilityOperation("invalid", "borrow", "owner", None, None, 3),
            ),
        )
        summary = build_ownership_summaries(model)["invalid"]
        self.assertEqual(summary.approximation.kind, ApproximationKind.UNKNOWN)
        self.assertEqual(summary.violations[0].code, "borrow-from-unavailable")

    def test_mutable_borrow_from_shared_capability_is_unknown(self) -> None:
        shared = CapabilityType(
            CapabilityKind.SHARE,
            "Buffer",
            state="Ready",
            raw="share Buffer[Ready]",
        )
        function = CapabilityFunction(
            "invalid_mut",
            ">",
            (CapabilityParam("shared", shared, 1),),
            shared,
            1,
            1,
            1,
        )
        model = model_with_capabilities(
            (function,),
            (
                CapabilityOperation(
                    "invalid_mut",
                    "borrow_mut",
                    "shared",
                    None,
                    None,
                    2,
                ),
            ),
        )
        summary = build_ownership_summaries(model)["invalid_mut"]
        self.assertEqual(summary.approximation.kind, ApproximationKind.UNKNOWN)
        self.assertEqual(
            summary.violations[0].code,
            "mutable-borrow-from-nonexclusive-capability",
        )


if __name__ == "__main__":
    unittest.main()

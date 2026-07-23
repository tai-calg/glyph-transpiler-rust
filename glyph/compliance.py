from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .schema import COMPLIANCE_REPORT_SCHEMA, IR_SCHEMA_VERSION


_VERIFICATION_CLASSES = frozenset({"static", "model", "runtime", "trusted"})


@dataclass(frozen=True)
class ComplianceRequirement:
    id: str
    axis: str
    statement: str
    verification_classes: tuple[str, ...]
    implementation: tuple[str, ...]
    positive_tests: tuple[str, ...]
    negative_tests: tuple[str, ...] = ()
    static_rule: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "axis": self.axis,
            "statement": self.statement,
            "verification_classes": list(self.verification_classes),
            "implementation": list(self.implementation),
            "positive_tests": list(self.positive_tests),
            "negative_tests": list(self.negative_tests),
            "static_rule": self.static_rule,
        }


REQUIREMENTS: tuple[ComplianceRequirement, ...] = (
    ComplianceRequirement(
        "NAME-001",
        "contract-namespace",
        "Object names and apostrophe-prefixed Contract names remain lexically distinct; bare Contract applications are rejected.",
        ("static",),
        ("glyph/contracts.py",),
        ("tests/test_contracts.py::ContractTests::test_contract_and_object_names_are_lexically_distinct",),
        ("tests/test_contracts.py::ContractTests::test_bare_name_cannot_be_used_as_contract",),
    ),
    ComplianceRequirement(
        "CAP-001",
        "capability",
        "Resource use requires an explicit capability and declared state.",
        ("static",),
        ("glyph/capabilities.py", "glyph/capability_model_validate.py"),
        ("tests/test_capabilities.py::CapabilityTests::test_resource_and_capability_types_are_erased_for_legacy_codegen",),
        (
            "tests/test_capabilities.py::CapabilityTests::test_resource_requires_capability_and_state",
            "tests/test_capabilities.py::CapabilityTests::test_unknown_resource_state_is_rejected",
        ),
    ),
    ComplianceRequirement(
        "CAP-002",
        "capability",
        "Affine values cannot be used after move.",
        ("static",),
        ("glyph/capabilities.py",),
        ("tests/test_capability_places.py::CapabilityPlaceTests::test_partial_field_moves_are_tracked_independently",),
        ("tests/test_capabilities.py::CapabilityTests::test_move_after_use_is_rejected",),
    ),
    ComplianceRequirement(
        "CAP-003",
        "capability",
        "Temporary borrows cannot escape into stored bindings.",
        ("static",),
        ("glyph/capabilities.py", "glyph/capability_surface_validate.py"),
        ("tests/test_capability_codegen.py::CapabilityCodegenTests::test_shared_clone_is_checked_then_erased_for_legacy_codegen",),
        ("tests/test_capabilities.py::CapabilityTests::test_borrow_cannot_escape_into_binding",),
    ),
    ComplianceRequirement(
        "CAP-004",
        "capability",
        "Shared or linked values cannot yield an exclusive mutable borrow.",
        ("static",),
        ("glyph/capabilities.py", "glyph/capability_surface_validate.py"),
        ("tests/test_acceptance_glyph04.py::Glyph04AcceptanceTests::test_complete_glyph04_system_generates_all_layers",),
        ("tests/test_capabilities.py::CapabilityTests::test_share_cannot_be_mutably_borrowed",),
    ),
    ComplianceRequirement(
        "CAP-005",
        "capability",
        "Only the declared identity-preserving capability conversions are accepted.",
        ("static", "trusted"),
        ("glyph/capabilities.py", "glyph/capability_codegen.py"),
        ("tests/test_capabilities.py::CapabilityTests::test_capability_casts_are_checked",),
        ("tests/test_capabilities.py::CapabilityTests::test_capability_casts_are_checked",),
    ),
    ComplianceRequirement(
        "CAP-006",
        "capability-place",
        "Aggregate resource fields are tracked as independent places and unresolved fields remain obligations.",
        ("static",),
        ("glyph/capability_places.py", "glyph/capabilities.py"),
        ("tests/test_capability_places.py::CapabilityPlaceTests::test_partial_field_moves_are_tracked_independently",),
        ("tests/test_capability_places.py::CapabilityPlaceTests::test_unresolved_resource_field_is_rejected",),
    ),
    ComplianceRequirement(
        "RES-001",
        "resource",
        "Every failure path preserves each owned resource with its capability and state.",
        ("static",),
        ("glyph/capabilities.py", "glyph/capability_model_validate.py"),
        ("tests/test_capabilities.py::CapabilityTests::test_failure_path_must_keep_owned_resource",),
        ("tests/test_capabilities.py::CapabilityTests::test_failure_path_must_keep_owned_resource",),
    ),
    ComplianceRequirement(
        "RES-002",
        "resource-identity",
        "State transitions and success/failure exits preserve one symbolic resource identity.",
        ("static",),
        ("glyph/resource_flow.py",),
        (
            "tests/test_resource_flow.py::ResourceFlowTests::test_state_transition_preserves_symbolic_identity",
            "tests/test_resource_flow.py::ResourceFlowTests::test_failure_and_success_paths_keep_same_resource_identity",
        ),
        ("tests/test_capabilities.py::CapabilityTests::test_failure_path_must_keep_owned_resource",),
    ),
    ComplianceRequirement(
        "WORLD-001",
        "world",
        "Cross-locus calls require a Protocol and cannot transfer a borrow.",
        ("static", "trusted"),
        ("glyph/contract_semantics.py", "glyph/runtime_contract_validate.py"),
        ("tests/test_contract_semantics.py::ContractSemanticTests::test_cross_world_call_with_protocol_is_allowed",),
        (
            "tests/test_contract_semantics.py::ContractSemanticTests::test_cross_world_direct_call_requires_protocol",
            "tests/test_contract_semantics.py::ContractSemanticTests::test_cross_world_borrow_is_rejected",
        ),
    ),
    ComplianceRequirement(
        "WORLD-002",
        "region",
        "Strong capabilities cannot escape from a narrower Region into broader storage; links may outlive the target Region.",
        ("static", "trusted"),
        ("glyph/runtime_contract_validate.py",),
        ("tests/test_runtime_contract_validation.py::RuntimeContractValidationTests::test_link_may_outlive_target_region",),
        ("tests/test_runtime_contract_validation.py::RuntimeContractValidationTests::test_share_value_cannot_escape_to_broader_region",),
    ),
    ComplianceRequirement(
        "PROTO-001",
        "protocol",
        "Protocol direction uses -> and <- and the resulting trace must match the applied function signature.",
        ("static", "trusted"),
        ("glyph/contract_semantics.py", "glyph/contracts.py"),
        (
            "tests/test_contracts.py::ContractTests::test_protocol_uses_unambiguous_arrows",
            "tests/test_contract_semantics.py::ContractSemanticTests::test_world_protocol_handler_law_bundle_is_canonicalized",
        ),
        (
            "tests/test_contracts.py::ContractTests::test_protocol_uses_unambiguous_arrows",
            "tests/test_contract_semantics.py::ContractSemanticTests::test_protocol_signature_mismatch_is_rejected",
        ),
    ),
    ComplianceRequirement(
        "HANDLER-001",
        "handler-retry",
        "Retry requires a positive count, a Result target, and an explicit idempotency contract.",
        ("static", "runtime", "trusted"),
        ("glyph/contract_semantics.py", "glyph/runtime_contract_validate.py"),
        ("tests/test_contract_semantics.py::ContractSemanticTests::test_world_protocol_handler_law_bundle_is_canonicalized",),
        (
            "tests/test_contract_semantics.py::ContractSemanticTests::test_retry_requires_idempotency",
            "tests/test_contract_semantics.py::ContractSemanticTests::test_retry_target_must_return_result",
            "tests/test_runtime_contract_validation.py::RuntimeContractValidationTests::test_retry_count_must_be_positive",
        ),
    ),
    ComplianceRequirement(
        "HANDLER-002",
        "handler-recovery",
        "Recovery has one terminal action; rollback, compensation, and fallback targets are statically compatible.",
        ("static", "runtime", "trusted"),
        ("glyph/contract_semantics.py", "glyph/runtime_contract_validate.py"),
        ("tests/test_acceptance_glyph04.py::Glyph04AcceptanceTests::test_complete_glyph04_system_generates_all_layers",),
        (
            "tests/test_runtime_contract_validation.py::RuntimeContractValidationTests::test_handler_has_only_one_recovery_action",
            "tests/test_contract_semantics.py::ContractSemanticTests::test_rollback_requires_owned_resource_parameter",
            "tests/test_runtime_contract_validation.py::RuntimeContractValidationTests::test_compensation_must_reference_effect_boundary",
            "tests/test_runtime_contract_validation.py::RuntimeContractValidationTests::test_fallback_signature_must_match",
        ),
    ),
    ComplianceRequirement(
        "LAW-001",
        "law",
        "Product Laws lower into existing temporal monitors; function lifecycle Laws remain explicit runtime obligations.",
        ("model", "runtime"),
        ("glyph/contract_law_bridge.py", "glyph/temporal_codegen.py", "glyph/temporal_stream_codegen.py"),
        (
            "tests/test_contract_law_bridge.py::ContractLawBridgeTests::test_product_law_generates_existing_temporal_monitor",
            "tests/test_contract_law_bridge.py::ContractLawBridgeTests::test_function_lifecycle_law_stays_runtime_contract_only",
        ),
        (),
        static_rule=False,
    ),
    ComplianceRequirement(
        "BUNDLE-001",
        "bundle",
        "Bundle expansion permits one World, Protocol, and Handler while composing multiple Laws.",
        ("static",),
        ("glyph/contracts.py", "glyph/contract_semantics.py"),
        ("tests/test_contract_semantics.py::ContractSemanticTests::test_world_protocol_handler_law_bundle_is_canonicalized",),
        (
            "tests/test_contract_semantics.py::ContractSemanticTests::test_bundle_rejects_two_worlds",
            "tests/test_contracts.py::ContractTests::test_contract_cycle_is_rejected",
        ),
    ),
    ComplianceRequirement(
        "IR-001",
        "public-ir",
        "Glyph 0.4 IR schemas and verification classes are versioned and emitted only for opted-in sources.",
        ("static",),
        ("glyph/schema.py", "glyph/compilation.py", "glyph/verification.py"),
        (
            "tests/test_acceptance_glyph04.py::Glyph04AcceptanceTests::test_complete_glyph04_system_generates_all_layers",
            "tests/test_verification_report.py::VerificationReportTests::test_glyph04_reports_static_runtime_and_trusted_boundaries",
        ),
        ("tests/test_verification_report.py::VerificationReportTests::test_plain_source_keeps_old_artifact_set",),
    ),
    ComplianceRequirement(
        "COMPAT-001",
        "backward-compatibility",
        "Legacy sources preserve generated Rust, public JSON, diagrams, diagnostics, and exit status against main.",
        ("static",),
        ("scripts/verify_glyph04_compat.py", ".github/workflows/ci.yml"),
        ("tests/test_contracts.py::ContractTests::test_contract_layer_does_not_change_generated_rust",),
        (),
        static_rule=False,
    ),
)


@dataclass(frozen=True)
class ComplianceReport:
    requirements: tuple[ComplianceRequirement, ...]
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, object]:
        by_axis: dict[str, int] = {}
        by_class: dict[str, int] = {}
        for requirement in self.requirements:
            by_axis[requirement.axis] = by_axis.get(requirement.axis, 0) + 1
            for item in requirement.verification_classes:
                by_class[item] = by_class.get(item, 0) + 1
        return {
            "schema": COMPLIANCE_REPORT_SCHEMA,
            "version": IR_SCHEMA_VERSION,
            "status": "passed" if self.passed else "failed",
            "summary": {
                "requirements": len(self.requirements),
                "by_axis": by_axis,
                "by_verification_class": by_class,
                "errors": len(self.errors),
            },
            "requirements": [item.to_dict() for item in self.requirements],
            "errors": list(self.errors),
        }


def _test_id_exists(root: Path, test_id: str) -> str | None:
    parts = test_id.split("::")
    if len(parts) != 3:
        return f"invalid test evidence id '{test_id}'"
    relative, class_name, method_name = parts
    path = root / relative
    if not path.is_file():
        return f"test evidence file does not exist: {relative}"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return f"cannot parse test evidence {relative}: {exc}"
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        if any(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == method_name
            for item in node.body
        ):
            return None
        return f"test method does not exist: {test_id}"
    return f"test class does not exist: {test_id}"


def validate_compliance_manifest(
    root: str | Path,
    requirements: Iterable[ComplianceRequirement] = REQUIREMENTS,
) -> tuple[str, ...]:
    repository = Path(root)
    errors: list[str] = []
    seen: set[str] = set()
    for requirement in requirements:
        if requirement.id in seen:
            errors.append(f"duplicate requirement id: {requirement.id}")
        seen.add(requirement.id)
        unknown = set(requirement.verification_classes) - _VERIFICATION_CLASSES
        if unknown:
            errors.append(
                f"{requirement.id}: unknown verification classes: {', '.join(sorted(unknown))}"
            )
        if not requirement.implementation:
            errors.append(f"{requirement.id}: no implementation evidence")
        for relative in requirement.implementation:
            if not (repository / relative).is_file():
                errors.append(f"{requirement.id}: implementation file does not exist: {relative}")
        if not requirement.positive_tests:
            errors.append(f"{requirement.id}: no positive test evidence")
        if requirement.static_rule and not requirement.negative_tests:
            errors.append(f"{requirement.id}: static rule has no negative test evidence")
        for test_id in (*requirement.positive_tests, *requirement.negative_tests):
            error = _test_id_exists(repository, test_id)
            if error is not None:
                errors.append(f"{requirement.id}: {error}")
    return tuple(errors)


def build_compliance_report(root: str | Path) -> ComplianceReport:
    return ComplianceReport(REQUIREMENTS, validate_compliance_manifest(root))

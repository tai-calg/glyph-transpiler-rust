from __future__ import annotations

from .abstract_evidence_shadow import (
    RTAI_ABSTRACT_EVIDENCE_SHADOW_VERSION,
    attach_rtai_abstract_execution_evidence,
)
from .abstract_solver import AbstractInterpreter
from .abstract_state import (
    AbstractAnalysisResult,
    AnalysisBudget,
    GuardedAlternative,
)
from .analysis_evidence import (
    ABSTRACT_EVIDENCE_ADAPTER_VERSION,
    AbstractEvidenceContext,
    VerifiedReachabilityWitness,
    context_evidence_from_analysis,
    edge_evidence_from_analysis,
    verified_reachability_witness,
)
from .bootstrap import (
    RTAI_SEMANTIC_BOOTSTRAP_VERSION,
    attach_rtai_semantic_bootstrap,
)
from .concrete import (
    ConcreteExecutionResult,
    ConcreteInterpreter,
    ConstructorValue,
    ResultValue,
    VariantValue,
)
from .effect_contract import (
    EFFECT_CONTRACT_REGISTRY_VERSION,
    VerifiedEffectContract,
    VerifiedEffectContractRegistry,
    read_only_identity_contract,
    reviewed_deterministic_contract,
)
from .effect_contract_audit import (
    EFFECT_CONTRACT_AUDIT_VERSION,
    EffectContractCoverageReport,
    EffectContractEntryCoverage,
    audit_effect_contract_coverage,
)
from .evidence import EXECUTION_EVIDENCE_SCHEMA, EXECUTION_EVIDENCE_VERSION
from .evidence_projection import (
    EVIDENCE_PROJECTION_VERSION,
    EvidenceProjectionMode,
    ProjectionReadinessReport,
    TransitionProjectionReadiness,
    audit_evidence_projection,
    project_machine_from_evidence,
)
from .function_summary import (
    FUNCTION_SUMMARY_VERSION,
    FunctionSummarySet,
    PureFunctionSummary,
    SummaryApplication,
    build_pure_function_summaries,
    inline_exact_pure_calls,
    instantiate_pure_summary,
)
from .legacy_shadow import attach_execution_evidence_v2
from .lowering import (
    LoweringIssue,
    LoweringReport,
    lower_compilation_model,
    lower_compilation_model_report,
    lower_function,
)
from .machine_relation import MachineRelation, build_machine_relation
from .native_projection_readiness import (
    NATIVE_EVIDENCE_READINESS_VERSION,
    attach_native_evidence_projection_readiness,
)
from .oracle import (
    AbstractCoverageCase,
    BoundedOracleReport,
    BoundedSoundnessReport,
    compare_bounded_ast_and_teir,
    compare_bounded_teir_and_abstract,
)
from .ownership_semantics import (
    OWNERSHIP_SEMANTICS_VERSION,
    OwnershipFunctionSummary,
    OwnershipViolation,
    build_ownership_summaries,
)
from .preimage import (
    PreimageStatus,
    TransitionCallPreimage,
    compute_transition_call_preimage,
)
from .projection import ExactActionDecision, check_exact_action_projection
from .public_effect_contracts import (
    BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID,
    PUBLIC_STRICT_EFFECT_SURFACE_VERSION,
    PUBLIC_STRICT_EXCLUSIONS,
    PUBLIC_STRICT_PROGRAMS,
    PublicEffectContractCase,
    PublicStrictExclusion,
    PublicStrictProgram,
    public_strict_program,
    public_strict_surface_ir,
)
from .reference import ReferenceInterpreter
from .semantic_status import (
    RTAI_SEMANTIC_STATUS_VERSION,
    attach_rtai_semantic_status,
)
from .stateful_concrete import (
    StatefulConcreteExecutionResult,
    StatefulConcreteInterpreter,
    StatefulEffectResult,
)
from .strict_projection_campaign import (
    STRICT_PROJECTION_CAMPAIGN_VERSION,
    build_strict_io_state_views,
    build_strict_projection_candidate,
)
from .summary_interpreter import (
    ContextualEffectSummaryRegistry,
    SummaryAwareAbstractInterpreter,
)
from .typed_smt import (
    TYPED_SMT_ENCODING_VERSION,
    SatModel,
    SolverOutcome,
    SolverUnknown,
    TypedConstraintSolver,
    TypedPredicateEncoder,
    UnsatProven,
)
from .view_edge_specialization import (
    VIEW_EDGE_SPECIALIZATION_VERSION,
    ViewEdgeBinding,
    ViewEdgeBindingStatus,
    attach_view_edge_specialization,
    specialize_view_edges,
)
from .witness_generation import (
    BoundedWitnessGenerationReport,
    GeneratedWitness,
    TargetedWitnessCase,
    TargetedWitnessRegistry,
    WITNESS_GENERATION_VERSION,
    WitnessEntryCoverage,
    WitnessGenerationIssue,
    generate_bounded_system_witnesses,
)


__all__ = [
    "ABSTRACT_EVIDENCE_ADAPTER_VERSION",
    "AbstractAnalysisResult",
    "AbstractCoverageCase",
    "AbstractEvidenceContext",
    "AbstractInterpreter",
    "AnalysisBudget",
    "BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID",
    "BoundedOracleReport",
    "BoundedSoundnessReport",
    "BoundedWitnessGenerationReport",
    "ConcreteExecutionResult",
    "ConcreteInterpreter",
    "ConstructorValue",
    "ContextualEffectSummaryRegistry",
    "EFFECT_CONTRACT_AUDIT_VERSION",
    "EFFECT_CONTRACT_REGISTRY_VERSION",
    "EVIDENCE_PROJECTION_VERSION",
    "EXECUTION_EVIDENCE_SCHEMA",
    "EXECUTION_EVIDENCE_VERSION",
    "EffectContractCoverageReport",
    "EffectContractEntryCoverage",
    "EvidenceProjectionMode",
    "ExactActionDecision",
    "FUNCTION_SUMMARY_VERSION",
    "FunctionSummarySet",
    "GeneratedWitness",
    "GuardedAlternative",
    "LoweringIssue",
    "LoweringReport",
    "MachineRelation",
    "NATIVE_EVIDENCE_READINESS_VERSION",
    "OWNERSHIP_SEMANTICS_VERSION",
    "OwnershipFunctionSummary",
    "OwnershipViolation",
    "PUBLIC_STRICT_EFFECT_SURFACE_VERSION",
    "PUBLIC_STRICT_EXCLUSIONS",
    "PUBLIC_STRICT_PROGRAMS",
    "PreimageStatus",
    "ProjectionReadinessReport",
    "PublicEffectContractCase",
    "PublicStrictExclusion",
    "PublicStrictProgram",
    "PureFunctionSummary",
    "RTAI_ABSTRACT_EVIDENCE_SHADOW_VERSION",
    "RTAI_SEMANTIC_BOOTSTRAP_VERSION",
    "RTAI_SEMANTIC_STATUS_VERSION",
    "ReferenceInterpreter",
    "ResultValue",
    "STRICT_PROJECTION_CAMPAIGN_VERSION",
    "SatModel",
    "SolverOutcome",
    "SolverUnknown",
    "StatefulConcreteExecutionResult",
    "StatefulConcreteInterpreter",
    "StatefulEffectResult",
    "SummaryApplication",
    "SummaryAwareAbstractInterpreter",
    "TYPED_SMT_ENCODING_VERSION",
    "TargetedWitnessCase",
    "TargetedWitnessRegistry",
    "TransitionCallPreimage",
    "TransitionProjectionReadiness",
    "TypedConstraintSolver",
    "TypedPredicateEncoder",
    "UnsatProven",
    "VIEW_EDGE_SPECIALIZATION_VERSION",
    "VariantValue",
    "VerifiedEffectContract",
    "VerifiedEffectContractRegistry",
    "VerifiedReachabilityWitness",
    "ViewEdgeBinding",
    "ViewEdgeBindingStatus",
    "WITNESS_GENERATION_VERSION",
    "WitnessEntryCoverage",
    "WitnessGenerationIssue",
    "attach_execution_evidence_v2",
    "attach_native_evidence_projection_readiness",
    "attach_rtai_abstract_execution_evidence",
    "attach_rtai_semantic_bootstrap",
    "attach_rtai_semantic_status",
    "attach_view_edge_specialization",
    "audit_effect_contract_coverage",
    "audit_evidence_projection",
    "build_machine_relation",
    "build_ownership_summaries",
    "build_pure_function_summaries",
    "build_strict_io_state_views",
    "build_strict_projection_candidate",
    "check_exact_action_projection",
    "compare_bounded_ast_and_teir",
    "compare_bounded_teir_and_abstract",
    "compute_transition_call_preimage",
    "context_evidence_from_analysis",
    "edge_evidence_from_analysis",
    "generate_bounded_system_witnesses",
    "inline_exact_pure_calls",
    "instantiate_pure_summary",
    "lower_compilation_model",
    "lower_compilation_model_report",
    "lower_function",
    "project_machine_from_evidence",
    "public_strict_program",
    "public_strict_surface_ir",
    "read_only_identity_contract",
    "reviewed_deterministic_contract",
    "specialize_view_edges",
    "verified_reachability_witness",
]

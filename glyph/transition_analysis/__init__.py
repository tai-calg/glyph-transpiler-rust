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
from .reference import ReferenceInterpreter
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
    WITNESS_GENERATION_VERSION,
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
    "BoundedOracleReport",
    "BoundedSoundnessReport",
    "BoundedWitnessGenerationReport",
    "ConcreteExecutionResult",
    "ConcreteInterpreter",
    "ConstructorValue",
    "ContextualEffectSummaryRegistry",
    "EFFECT_CONTRACT_REGISTRY_VERSION",
    "EVIDENCE_PROJECTION_VERSION",
    "EXECUTION_EVIDENCE_SCHEMA",
    "EXECUTION_EVIDENCE_VERSION",
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
    "PreimageStatus",
    "ProjectionReadinessReport",
    "PureFunctionSummary",
    "RTAI_ABSTRACT_EVIDENCE_SHADOW_VERSION",
    "RTAI_SEMANTIC_BOOTSTRAP_VERSION",
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
    "WitnessGenerationIssue",
    "attach_execution_evidence_v2",
    "attach_native_evidence_projection_readiness",
    "attach_rtai_abstract_execution_evidence",
    "attach_rtai_semantic_bootstrap",
    "attach_view_edge_specialization",
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
    "read_only_identity_contract",
    "specialize_view_edges",
    "verified_reachability_witness",
]

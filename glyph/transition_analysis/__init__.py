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


__all__ = [
    "ABSTRACT_EVIDENCE_ADAPTER_VERSION",
    "AbstractAnalysisResult",
    "AbstractCoverageCase",
    "AbstractEvidenceContext",
    "AbstractInterpreter",
    "AnalysisBudget",
    "BoundedOracleReport",
    "BoundedSoundnessReport",
    "ConcreteExecutionResult",
    "ConcreteInterpreter",
    "ConstructorValue",
    "ContextualEffectSummaryRegistry",
    "EVIDENCE_PROJECTION_VERSION",
    "EXECUTION_EVIDENCE_SCHEMA",
    "EXECUTION_EVIDENCE_VERSION",
    "EvidenceProjectionMode",
    "ExactActionDecision",
    "FUNCTION_SUMMARY_VERSION",
    "FunctionSummarySet",
    "GuardedAlternative",
    "LoweringIssue",
    "LoweringReport",
    "MachineRelation",
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
    "VariantValue",
    "VerifiedReachabilityWitness",
    "attach_execution_evidence_v2",
    "attach_rtai_abstract_execution_evidence",
    "attach_rtai_semantic_bootstrap",
    "audit_evidence_projection",
    "build_machine_relation",
    "build_ownership_summaries",
    "build_pure_function_summaries",
    "check_exact_action_projection",
    "compare_bounded_ast_and_teir",
    "compare_bounded_teir_and_abstract",
    "compute_transition_call_preimage",
    "context_evidence_from_analysis",
    "edge_evidence_from_analysis",
    "inline_exact_pure_calls",
    "instantiate_pure_summary",
    "lower_compilation_model",
    "lower_compilation_model_report",
    "lower_function",
    "project_machine_from_evidence",
    "verified_reachability_witness",
]

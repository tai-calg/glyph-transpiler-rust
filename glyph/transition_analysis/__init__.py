from __future__ import annotations

from .abstract_solver import AbstractInterpreter
from .abstract_state import (
    AbstractAnalysisResult,
    AnalysisBudget,
    GuardedAlternative,
)
from .analysis_evidence import (
    ABSTRACT_EVIDENCE_ADAPTER_VERSION,
    AbstractEvidenceContext,
    context_evidence_from_analysis,
    edge_evidence_from_analysis,
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
    BoundedOracleReport,
    BoundedSoundnessReport,
    compare_bounded_ast_and_teir,
    compare_bounded_teir_and_abstract,
)
from .preimage import (
    PreimageStatus,
    TransitionCallPreimage,
    compute_transition_call_preimage,
)
from .projection import ExactActionDecision, check_exact_action_projection
from .reference import ReferenceInterpreter
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
    "AbstractEvidenceContext",
    "AbstractInterpreter",
    "AnalysisBudget",
    "BoundedOracleReport",
    "BoundedSoundnessReport",
    "ConcreteExecutionResult",
    "ConcreteInterpreter",
    "ConstructorValue",
    "EXECUTION_EVIDENCE_SCHEMA",
    "EXECUTION_EVIDENCE_VERSION",
    "ExactActionDecision",
    "GuardedAlternative",
    "LoweringIssue",
    "LoweringReport",
    "MachineRelation",
    "PreimageStatus",
    "RTAI_SEMANTIC_BOOTSTRAP_VERSION",
    "ReferenceInterpreter",
    "ResultValue",
    "SatModel",
    "SolverOutcome",
    "SolverUnknown",
    "TYPED_SMT_ENCODING_VERSION",
    "TransitionCallPreimage",
    "TypedConstraintSolver",
    "TypedPredicateEncoder",
    "UnsatProven",
    "VariantValue",
    "attach_execution_evidence_v2",
    "attach_rtai_semantic_bootstrap",
    "build_machine_relation",
    "check_exact_action_projection",
    "compare_bounded_ast_and_teir",
    "compare_bounded_teir_and_abstract",
    "compute_transition_call_preimage",
    "context_evidence_from_analysis",
    "edge_evidence_from_analysis",
    "lower_compilation_model",
    "lower_compilation_model_report",
    "lower_function",
]

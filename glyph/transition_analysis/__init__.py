from __future__ import annotations

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
from .lowering import lower_compilation_model, lower_function
from .machine_relation import MachineRelation, build_machine_relation
from .oracle import BoundedOracleReport, compare_bounded_ast_and_teir
from .preimage import (
    PreimageStatus,
    TransitionCallPreimage,
    compute_transition_call_preimage,
)
from .projection import ExactActionDecision, check_exact_action_projection
from .reference import ReferenceInterpreter


__all__ = [
    "BoundedOracleReport",
    "ConcreteExecutionResult",
    "ConcreteInterpreter",
    "ConstructorValue",
    "EXECUTION_EVIDENCE_SCHEMA",
    "EXECUTION_EVIDENCE_VERSION",
    "ExactActionDecision",
    "MachineRelation",
    "PreimageStatus",
    "RTAI_SEMANTIC_BOOTSTRAP_VERSION",
    "ReferenceInterpreter",
    "ResultValue",
    "TransitionCallPreimage",
    "VariantValue",
    "attach_execution_evidence_v2",
    "attach_rtai_semantic_bootstrap",
    "build_machine_relation",
    "check_exact_action_projection",
    "compare_bounded_ast_and_teir",
    "compute_transition_call_preimage",
    "lower_compilation_model",
    "lower_function",
]

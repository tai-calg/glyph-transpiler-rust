from __future__ import annotations

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
    "ReferenceInterpreter",
    "ResultValue",
    "VariantValue",
    "attach_execution_evidence_v2",
    "build_machine_relation",
    "check_exact_action_projection",
    "compare_bounded_ast_and_teir",
    "lower_compilation_model",
    "lower_function",
]

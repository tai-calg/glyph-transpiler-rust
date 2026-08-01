from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from .._transition_branch_semantics import (
    build_machine_branch_context,
    simplify_expr,
    substitute_expr,
)
from ..artifacts import CompilationModel
from ..compiler import BinaryExpr, BoolExpr, Expr, TypeRef
from .exactness import (
    Approximation,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)
from .machine_relation import EdgeSpec, build_machine_relation
from .type_environment import unique_parameter_types
from .typed_smt import (
    SatModel,
    SolverResult,
    TypedConstraintSolver,
    UnsatProven,
)


class PreimageStatus(str, Enum):
    PROVEN_FALSE = "proven-false"
    PROVEN_TRUE = "proven-true"
    SAT_MODEL = "sat-model"
    SYMBOLIC = "symbolic"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EdgePreimage:
    edge_id: str
    condition: Expr
    status: PreimageStatus
    result_expression: Expr
    approximation: Approximation
    solver_result: SolverResult

    def to_ir(self) -> dict[str, object]:
        return {
            "edge_id": self.edge_id,
            "condition": repr(self.condition),
            "status": self.status.value,
            "result_expression": repr(self.result_expression),
            "approximation": self.approximation.to_ir(),
            "solver_result": self.solver_result.to_ir(),
        }


@dataclass(frozen=True)
class TransitionCallPreimage:
    machine_id: str
    transition_function: str
    actual_arguments: tuple[Expr, ...]
    caller_condition: Expr
    edges: tuple[EdgePreimage, ...]
    approximation: Approximation

    def to_ir(self) -> dict[str, object]:
        return {
            "machine_id": self.machine_id,
            "transition_function": self.transition_function,
            "actual_arguments": [repr(argument) for argument in self.actual_arguments],
            "caller_condition": repr(self.caller_condition),
            "edges": [edge.to_ir() for edge in self.edges],
            "approximation": self.approximation.to_ir(),
        }


def compute_transition_call_preimage(
    model: CompilationModel,
    machine_name: str,
    actual_arguments: Sequence[Expr],
    *,
    caller_condition: Expr = BoolExpr(True),
    type_environment: Mapping[str, TypeRef] | None = None,
    solver: TypedConstraintSolver | None = None,
) -> TransitionCallPreimage | None:
    """Compute caller-path and normalized-Machine-edge relational preimages."""

    relation = build_machine_relation(model, machine_name)
    context = build_machine_branch_context(model, machine_name)
    if relation is None or context is None:
        return None
    if len(actual_arguments) != len(relation.formals):
        return TransitionCallPreimage(
            relation.machine_id,
            relation.transition_function,
            tuple(actual_arguments),
            caller_condition,
            (),
            Approximation.unknown("transition-argument-arity-mismatch"),
        )

    substitution = dict(zip(relation.formals, actual_arguments, strict=True))
    caller = simplify_expr(
        caller_condition,
        products=context.products,
        constants=context.constants,
    )
    active_solver = solver or TypedConstraintSolver(model)
    edges = tuple(
        _edge_preimage(
            model,
            edge,
            substitution,
            caller,
            products=context.products,
            constants=context.constants,
            type_environment=type_environment,
            solver=active_solver,
        )
        for edge in relation.edges
    )
    approximation = Approximation.combine(
        (relation.approximation, *(edge.approximation for edge in edges))
    )
    return TransitionCallPreimage(
        relation.machine_id,
        relation.transition_function,
        tuple(actual_arguments),
        caller,
        edges,
        approximation,
    )


def _edge_preimage(
    model: CompilationModel,
    edge: EdgeSpec,
    substitution: Mapping[str, Expr],
    caller_condition: Expr,
    *,
    products: Mapping[str, object],
    constants: frozenset[str],
    type_environment: Mapping[str, TypeRef] | None,
    solver: TypedConstraintSolver,
) -> EdgePreimage:
    condition = simplify_expr(
        _and(
            caller_condition,
            substitute_expr(edge.effective_guard, substitution),
        ),
        products=products,  # type: ignore[arg-type]
        constants=constants,
    )
    result = simplify_expr(
        substitute_expr(edge.result_expression, substitution),
        products=products,  # type: ignore[arg-type]
        constants=constants,
    )
    environment = (
        dict(type_environment)
        if type_environment is not None
        else unique_parameter_types(model, condition)
    )
    solver_result: SolverResult
    if isinstance(condition, BoolExpr):
        solver_result = (
            SatModel(())
            if condition.value
            else UnsatProven("predicate simplified to literal false")
        )
    else:
        solver_result = solver.solve(condition, environment)

    if isinstance(solver_result, UnsatProven):
        status = PreimageStatus.PROVEN_FALSE
    elif isinstance(solver_result, SatModel):
        status = (
            PreimageStatus.PROVEN_TRUE
            if isinstance(condition, BoolExpr) and condition.value
            else PreimageStatus.SAT_MODEL
        )
    elif type_environment is None and not environment:
        status = PreimageStatus.SYMBOLIC
    else:
        status = PreimageStatus.UNKNOWN

    proof = ExactnessProof(
        ExactnessProofKind.STRUCTURAL_IDENTITY,
        ExactnessProofScope.TRANSITION_PREIMAGE,
        f"formal substitution into normalized edge {edge.edge_id}",
    )
    return EdgePreimage(
        edge.edge_id,
        condition,
        status,
        result,
        Approximation.exact(proof),
        solver_result,
    )


def _and(left: Expr, right: Expr) -> Expr:
    if isinstance(left, BoolExpr):
        return right if left.value else left
    if isinstance(right, BoolExpr):
        return left if right.value else right
    return BinaryExpr("&", left, right)

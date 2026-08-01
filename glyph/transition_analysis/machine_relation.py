from __future__ import annotations

from dataclasses import dataclass

from .. import _transition_branch_semantics as branch_semantics
from .._transition_branch_semantics import (
    MachineBranchContext,
    TransitionBranch,
    build_machine_branch_context,
    simplify_expr,
)
from ..artifacts import CompilationModel
from ..compiler import BinaryExpr, BoolExpr, Expr, FunctionDecl, NameExpr, TryExpr, UnaryExpr
from .exactness import (
    Approximation,
    ApproximationCause,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)


@dataclass(frozen=True)
class EdgeSpec:
    """One ordered first-match branch of a Machine transition relation."""

    edge_id: str
    ordinal: int
    effective_guard: Expr
    result_expression: Expr
    target_state: str
    completion: str
    source_line: int

    def to_ir(self) -> dict[str, object]:
        return {
            "edge_id": self.edge_id,
            "ordinal": self.ordinal,
            "effective_guard": repr(self.effective_guard),
            "result_expression": repr(self.result_expression),
            "target_state": self.target_state,
            "completion": self.completion,
            "source_line": self.source_line,
        }


@dataclass(frozen=True)
class MachineRelation:
    machine_id: str
    transition_function: str
    formals: tuple[str, ...]
    edges: tuple[EdgeSpec, ...]
    approximation: Approximation

    def to_ir(self) -> dict[str, object]:
        return {
            "machine_id": self.machine_id,
            "transition_function": self.transition_function,
            "formals": list(self.formals),
            "edges": [edge.to_ir() for edge in self.edges],
            "approximation": self.approximation.to_ir(),
        }


def build_machine_relation(
    model: CompilationModel,
    machine_name: str,
) -> MachineRelation | None:
    """Normalize Glyph's ordered Machine guards exactly once.

    The source function's branch order is part of Glyph semantics. For source
    guards ``g1, g2, ...`` this constructs ``g1``, ``!g1 & g2``, ... and the
    final fallback ``!g1 & !g2 ...``. System analysis consumes these effective
    guards and must not reinterpret the original guard list.

    Function blocks lower local bindings through unguarded continuation helpers.
    The final guarded value helper must be resolved through those continuations;
    otherwise a valid block-local decision would incorrectly produce an empty
    Machine relation.
    """

    context = build_machine_branch_context(model, machine_name)
    if context is None:
        return None
    declaration = context.functions.get(context.next_function)
    if declaration is None:
        return None

    branches = _resolved_relation_branches(context, declaration)
    remaining: Expr = BoolExpr(True)
    edges: list[EdgeSpec] = []
    for ordinal, branch in enumerate(branches):
        raw_guard = branch.condition
        effective = remaining if raw_guard is None else _and(remaining, raw_guard)
        effective = simplify_expr(
            effective,
            products=context.products,
            constants=context.constants,
        )
        edge_id = f"{machine_name}:{context.next_function}:{branch.line}:{ordinal}"
        edges.append(
            EdgeSpec(
                edge_id=edge_id,
                ordinal=ordinal,
                effective_guard=effective,
                result_expression=branch.value,
                target_state=branch.target,
                completion=(
                    "may-propagate-failure"
                    if _contains_try(branch.value)
                    else "returns-normally"
                ),
                source_line=branch.line,
            )
        )
        if raw_guard is not None:
            remaining = _and(remaining, UnaryExpr("!", raw_guard))

    if not edges:
        return MachineRelation(
            machine_id=machine_name,
            transition_function=context.next_function,
            formals=tuple(parameter.name for parameter in declaration.params),
            edges=(),
            approximation=Approximation.unknown(
                ApproximationCause.UNSUPPORTED_EXPRESSION,
                "machine-relation-branches-unavailable",
            ),
        )

    proof = ExactnessProof(
        ExactnessProofKind.STRUCTURAL_IDENTITY,
        ExactnessProofScope.MACHINE_RELATION,
        f"ordered first-match normalization for machine {machine_name}",
    )
    return MachineRelation(
        machine_id=machine_name,
        transition_function=context.next_function,
        formals=tuple(parameter.name for parameter in declaration.params),
        edges=tuple(edges),
        approximation=Approximation.exact(proof),
    )


def _resolved_relation_branches(
    context: MachineBranchContext,
    declaration: FunctionDecl,
) -> tuple[TransitionBranch, ...]:
    if context.branches:
        return context.branches
    if declaration.expression is None:
        return ()

    inlined = branch_semantics._inline_unguarded(  # noqa: SLF001 - shared semantic core
        declaration.expression,
        context.functions,
    )
    call = branch_semantics._unwrap_call(inlined)  # noqa: SLF001
    if call is None or not isinstance(call.callee, NameExpr):
        return ()
    nested = context.functions.get(call.callee.name)
    if nested is None or not nested.guards:
        return ()
    bindings = branch_semantics._call_bindings(nested, call)  # noqa: SLF001
    if bindings is None:
        return ()
    return tuple(
        branch_semantics._trace_function(  # noqa: SLF001
            nested.name,
            functions=context.functions,
            state_decl=context.state_decl,
            selector_index=context.selector_index,
            variants=context.selector_variants,
            root_state_param=context.machine.state_param.name,
            bindings=bindings,
            inherited_condition=None,
            visited=(context.next_function,),
        )
    )


def relation_by_transition_function(
    model: CompilationModel,
) -> dict[str, MachineRelation]:
    relations: dict[str, MachineRelation] = {}
    for machine in model.machines:
        relation = build_machine_relation(model, machine.name)
        if relation is not None:
            relations[relation.transition_function] = relation
    return relations


def _and(left: Expr, right: Expr) -> Expr:
    if isinstance(left, BoolExpr):
        return right if left.value else left
    if isinstance(right, BoolExpr):
        return left if right.value else right
    return BinaryExpr("&", left, right)


def _contains_try(expression: Expr) -> bool:
    if isinstance(expression, TryExpr):
        return True
    for value in vars(expression).values() if hasattr(expression, "__dict__") else ():
        if isinstance(value, Expr) and _contains_try(value):
            return True
        if isinstance(value, tuple) and any(
            isinstance(item, Expr) and _contains_try(item) for item in value
        ):
            return True
    return False

from __future__ import annotations

from typing import Sequence

from ._boolean_reasoning import propositional_truth
from ._transition_branch_semantics import (
    MachineBranchContext,
    PlannedTransitionBranch,
    _source_state_value,
    simplify_expr,
    substitute_expr,
)
from .compiler import BoolExpr, Expr


def specialize_for_source(
    context: MachineBranchContext,
    expression: Expr,
    source_state: str,
) -> Expr:
    substituted = substitute_expr(
        expression,
        {
            context.machine.state_param.name: _source_state_value(
                context,
                source_state,
            )
        },
    )
    return simplify_expr(
        substituted,
        products=context.products,
        constants=context.constants,
    )


def semantic_truth_value(
    expression: Expr,
    *,
    context: MachineBranchContext,
) -> bool | None:
    simplified = simplify_expr(
        expression,
        products=context.products,
        constants=context.constants,
    )
    if isinstance(simplified, BoolExpr):
        return simplified.value
    return propositional_truth(simplified)


def planned_source_branches(
    context: MachineBranchContext,
    state_names: Sequence[str],
    *,
    unreachable_lines: frozenset[int] = frozenset(),
) -> tuple[PlannedTransitionBranch, ...]:
    """Plan an ordered decision list independently for every source state.

    Source-state predicates and product projections are simplified first. The
    remaining boolean structure is then reduced canonically, so tautologies and
    contradictions such as ``x | !x`` and ``x & !x`` exhaust or eliminate a
    branch exactly rather than leaking into the final wildcard.
    """

    exhausted = {state_name: False for state_name in state_names}
    planned: list[PlannedTransitionBranch] = []
    for branch in context.branches:
        if branch.line in unreachable_lines:
            continue
        for source_state in state_names:
            if exhausted[source_state]:
                continue
            condition_truth = True
            if branch.condition is not None:
                condition_truth = semantic_truth_value(
                    specialize_for_source(context, branch.condition, source_state),
                    context=context,
                )
            if condition_truth is False:
                continue
            target_state = (
                source_state if branch.target == "__same__" else branch.target
            )
            if target_state not in state_names:
                continue
            planned.append(
                PlannedTransitionBranch(
                    branch=branch,
                    source_state=source_state,
                    target_state=target_state,
                    value=specialize_for_source(
                        context,
                        branch.value,
                        source_state,
                    ),
                )
            )
            if condition_truth is True:
                exhausted[source_state] = True
    return tuple(planned)

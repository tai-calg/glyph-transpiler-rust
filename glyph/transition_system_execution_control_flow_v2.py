from __future__ import annotations

from copy import deepcopy
from typing import Mapping, Sequence

from . import transition_system_execution_control_flow as _base
from ._transition_branch_semantics import (
    branch_value_for_transition,
    build_machine_branch_context,
    substitute_expr,
)
from ._transition_source_planning import planned_source_branches, semantic_truth_value
from .artifacts import CompilationModel
from .compiler import (
    AliasDecl,
    BinaryExpr,
    CallExpr,
    ExternDecl,
    Expr,
    NameExpr,
    TryExpr,
    TypeRef,
    parse_expr,
)
from .execution_ir import render_expr


_SUCCESS_VALUE_NAME = "__glyph_success_value__"


def _conditions_expression(conditions: Sequence[str]) -> Expr | None:
    combined: Expr | None = None
    for source in conditions:
        cleaned = source.strip()
        if not cleaned or cleaned == "true":
            continue
        try:
            expression = parse_expr(cleaned)
        except Exception:
            return None
        combined = expression if combined is None else BinaryExpr("&", combined, expression)
    return combined


def _conditions_are_feasible(
    conditions: Sequence[str],
    *,
    context: _base.MachineBranchContext,
) -> bool:
    expression = _conditions_expression(conditions)
    if expression is None:
        return True
    return semantic_truth_value(expression, context=context) is not False


def _prune_infeasible_cases(
    cases: Sequence[_base._Case],
    *,
    context: _base.MachineBranchContext,
) -> tuple[_base._Case, ...]:
    return _base._deduplicate_cases(
        [
            case
            for case in cases
            if _conditions_are_feasible(case.conditions, context=context)
        ]
    )


def _is_success_value(expression: Expr) -> bool:
    return (
        isinstance(expression, CallExpr)
        and isinstance(expression.callee, NameExpr)
        and expression.callee.name == _SUCCESS_VALUE_NAME
        and len(expression.args) == 1
    )


class _SystemExecutionEvaluator(_base._SystemExecutionEvaluator):
    """Path evaluator with feasible-path pruning and explicit `?` continuations."""

    def evaluate(
        self,
        pair: _base._ExprPair,
        site: _base._TraceSite,
        *,
        visited: frozenset[str] = frozenset(),
        after_transition: bool = False,
        conditions: tuple[str, ...] = (),
    ) -> tuple[_base._Case, ...]:
        symbolic = pair.symbolic
        concrete = pair.concrete
        if isinstance(symbolic, TryExpr) and isinstance(concrete, TryExpr):
            inner_cases = self.evaluate(
                _base._ExprPair(symbolic.expr, concrete.expr),
                site,
                visited=visited,
                after_transition=after_transition,
                conditions=conditions,
            )
            result: list[_base._Case] = []
            for inner in inner_cases:
                if inner.terminated:
                    result.append(inner)
                    continue
                rendered = render_expr(inner.value.concrete)
                success_condition = _base._append_condition(
                    inner.conditions,
                    f"success({rendered})",
                )
                failure_condition = _base._append_condition(
                    inner.conditions,
                    f"failure({rendered})",
                )
                success_value = _base._ExprPair(
                    CallExpr(NameExpr(_SUCCESS_VALUE_NAME), (inner.value.symbolic,)),
                    CallExpr(NameExpr(_SUCCESS_VALUE_NAME), (inner.value.concrete,)),
                )
                result.append(
                    _base._Case(
                        success_value,
                        inner.invocations,
                        inner.unresolved,
                        inner.transition_calls,
                        success_condition,
                    )
                )
                result.append(
                    _base._Case(
                        success_value,
                        inner.invocations,
                        inner.unresolved,
                        inner.transition_calls,
                        failure_condition,
                        True,
                        "failure-return",
                    )
                )
            return _prune_infeasible_cases(result, context=self._context)

        return _prune_infeasible_cases(
            super().evaluate(
                pair,
                site,
                visited=visited,
                after_transition=after_transition,
                conditions=conditions,
            ),
            context=self._context,
        )

    def _evaluate_call(
        self,
        symbolic: CallExpr,
        concrete: CallExpr,
        site: _base._TraceSite,
        *,
        visited: frozenset[str],
        after_transition: bool,
        conditions: tuple[str, ...],
    ) -> tuple[_base._Case, ...]:
        if _is_success_value(symbolic) and _is_success_value(concrete):
            return (
                _base._Case(
                    _base._ExprPair(symbolic, concrete),
                    conditions=conditions,
                ),
            )
        return super()._evaluate_call(
            symbolic,
            concrete,
            site,
            visited=visited,
            after_transition=after_transition,
            conditions=conditions,
        )


def _merge_block_state(
    state: _base._BlockState,
    result: _base._Case,
    *,
    binding_name: str | None = None,
) -> _base._BlockState:
    symbolic_values = dict(state.symbolic_values)
    concrete_values = dict(state.concrete_values)
    if binding_name is not None and not result.terminated:
        if _is_success_value(result.value.symbolic) and _is_success_value(
            result.value.concrete
        ):
            # `?` binds the successful payload once. Keep the source-level binding
            # name in later expressions instead of embedding or replaying the call.
            symbolic_values[binding_name] = NameExpr(binding_name)
            concrete_values[binding_name] = NameExpr(binding_name)
        else:
            symbolic_values[binding_name] = result.value.symbolic
            concrete_values[binding_name] = result.value.concrete
    return _base._BlockState(
        symbolic_values,
        concrete_values,
        (*state.invocations, *result.invocations),
        state.unresolved or result.unresolved,
        state.transition_calls + result.transition_calls,
        result.conditions,
        state.terminated or result.terminated,
        result.termination or state.termination,
    )


def _evaluate_block(
    context: _base._ExecutionContext,
    evaluator: _SystemExecutionEvaluator,
) -> _base._ContextEvaluation:
    assert context.block is not None
    states: list[_base._BlockState] = [_base._BlockState({}, {})]
    path = (context.entry,)
    for binding in context.block.bindings:
        next_states: list[_base._BlockState] = []
        for state in states:
            if state.terminated:
                next_states.append(state)
                continue
            site = _base._TraceSite(context.system, context.entry, binding.line, path)
            if binding.kind == "conditional":
                cases = _base._evaluate_conditional_binding(
                    binding.source,
                    state,
                    evaluator,
                    site,
                )
            else:
                try:
                    expression = parse_expr(binding.source)
                except Exception:
                    next_states.append(
                        _base._BlockState(
                            state.symbolic_values,
                            state.concrete_values,
                            state.invocations,
                            True,
                            state.transition_calls,
                            state.conditions,
                            state.terminated,
                            state.termination,
                        )
                    )
                    continue
                cases = evaluator.evaluate(
                    _base._ExprPair(
                        substitute_expr(expression, state.symbolic_values),
                        substitute_expr(expression, state.concrete_values),
                    ),
                    site,
                    after_transition=state.transition_calls > 0,
                    conditions=state.conditions,
                )
            next_states.extend(
                _merge_block_state(state, case, binding_name=binding.name)
                for case in cases
            )
        states = next_states

    final_states: list[_base._BlockState] = []
    for state in states:
        if state.terminated:
            final_states.append(state)
            continue
        try:
            expression = parse_expr(context.block.final_source)
        except Exception:
            final_states.append(
                _base._BlockState(
                    state.symbolic_values,
                    state.concrete_values,
                    state.invocations,
                    True,
                    state.transition_calls,
                    state.conditions,
                )
            )
            continue
        cases = evaluator.evaluate(
            _base._ExprPair(
                substitute_expr(expression, state.symbolic_values),
                substitute_expr(expression, state.concrete_values),
            ),
            _base._TraceSite(
                context.system,
                context.entry,
                context.block.final_line,
                path,
            ),
            after_transition=state.transition_calls > 0,
            conditions=state.conditions,
        )
        final_states.extend(_merge_block_state(state, case) for case in cases)

    return _base._ContextEvaluation(
        context,
        _base._deduplicate_cases(
            [
                _base._Case(
                    _base._ExprPair(NameExpr("_"), NameExpr("_")),
                    state.invocations,
                    state.unresolved,
                    state.transition_calls,
                    state.conditions,
                    state.terminated,
                    state.termination,
                )
                for state in final_states
            ]
        ),
    )


def _diagnostic(code: str, message: str, line: int) -> dict[str, object]:
    return {"severity": "warning", "code": code, "message": message, "line": line}


def attach_transition_system_execution_actions(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Attach complete, feasible System execution contexts to each machine edge."""

    result = deepcopy(machine_view)
    branch_context = build_machine_branch_context(model, str(result.get("name") or ""))
    if branch_context is None:
        return result
    functions = branch_context.functions
    contexts = _base._execution_contexts(model, functions)
    externs = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, ExternDecl)
    }
    aliases: Mapping[str, TypeRef] = {
        item.name: item.target
        for item in model.program.declarations
        if isinstance(item, AliasDecl)
    }
    state_names = [str(item.get("name", "")) for item in result.get("states", [])]
    unreachable_lines = frozenset(map(int, result.get("unreachable_branches", [])))
    branch_plan = planned_source_branches(
        branch_context,
        state_names,
        unreachable_lines=unreachable_lines,
    )
    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
    transitions: list[dict[str, object]] = []
    binding_count = 0
    actionless_count = 0
    conditional_count = 0
    unresolved_count = 0
    multiple_count = 0

    for original in result.get("transitions", []):
        transition = dict(original)
        branch_value = branch_value_for_transition(
            branch_context,
            transition,
            branch_plan,
        )
        if branch_value is None:
            transition["execution_action_bindings"] = []
            transition["execution_contexts"] = []
            transitions.append(transition)
            continue
        source = transition.get("source", {})
        line = int(source.get("line", 1)) if isinstance(source, Mapping) else 1
        bindings: list[dict[str, object]] = []
        for context in contexts:
            evaluator = _SystemExecutionEvaluator(
                branch_context=branch_context,
                externs=externs,
                aliases=aliases,
                branch_value=branch_value,
            )
            evaluation = (
                _evaluate_block(context, evaluator)
                if context.block is not None
                else _base._evaluate_function(context, evaluator)
            )
            binding = _base._binding(evaluation)
            if binding is None:
                continue
            bindings.append(binding)
            binding_count += 1
            status = binding.get("status")
            if binding.get("action") is None:
                actionless_count += 1
            if status == "conditional":
                conditional_count += 1
            elif status == "unresolved":
                unresolved_count += 1
                _base._append_diagnostic_once(
                    diagnostics,
                    _diagnostic(
                        _base._UNRESOLVED_CODE,
                        (
                            f"system `{context.system}` entry `{context.entry}` has a path "
                            f"through `{branch_context.next_function}` whose post-transition "
                            "execution cannot be proven"
                        ),
                        line,
                    ),
                )
            elif status == "multiple-transition-calls":
                multiple_count += 1
                _base._append_diagnostic_once(
                    diagnostics,
                    _diagnostic(
                        _base._MULTIPLE_CALLS_CODE,
                        (
                            f"system `{context.system}` entry `{context.entry}` invokes "
                            f"`{branch_context.next_function}` more than once on a feasible path"
                        ),
                        line,
                    ),
                )
        transition["execution_action_bindings"] = bindings
        transition["execution_contexts"] = [dict(item) for item in bindings]
        transitions.append(transition)

    analysis = dict(result.get("analysis", {}))
    analysis.update(
        {
            "execution_action_context_count": len(contexts),
            "execution_action_binding_count": binding_count,
            "execution_action_actionless_count": actionless_count,
            "execution_action_conditional_count": conditional_count,
            "execution_action_unresolved_count": unresolved_count,
            "execution_action_multiple_transition_call_count": multiple_count,
        }
    )
    result["transitions"] = transitions
    result["diagnostics"] = diagnostics
    result["analysis"] = analysis
    return result


def attach_transition_result_consumer_actions(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Compatibility name for the complete System execution analysis."""

    return attach_transition_system_execution_actions(model, machine_view)


__all__ = [
    "attach_transition_result_consumer_actions",
    "attach_transition_system_execution_actions",
]

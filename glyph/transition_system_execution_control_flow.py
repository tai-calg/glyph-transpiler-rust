from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping, Sequence

from . import _transition_system_execution_core as _base
from ._transition_branch_semantics import (
    branch_value_for_transition,
    build_machine_branch_context,
    _inline_unguarded,
    substitute_expr,
    unwrap_expr,
)
from ._transition_source_planning import planned_source_branches, semantic_truth_value
from .artifacts import CompilationModel
from .compiler import (
    AliasDecl,
    BinaryExpr,
    CallExpr,
    ExternDecl,
    Expr,
    FieldExpr,
    NameExpr,
    TryExpr,
    TypeRef,
    parse_expr,
)
from .execution_ir import render_expr


_SUCCESS_VALUE_NAME = "__glyph_success_value__"
_UNPROVEN_STATE_INPUT_CODE = "STIR_SYSTEM_STATE_INPUT_UNPROVEN"
_UNPROVEN_TRANSITION_ARGUMENT_CODE = "STIR_SYSTEM_TRANSITION_ARGUMENT_UNPROVEN"
_UNPROVEN_TRANSITION_VALUE_NAME = "__glyph_unproven_transition_result__"


@dataclass(frozen=True)
class _SystemWiringEvidence:
    explicit: bool
    valid_context: bool
    entry_inputs: frozenset[str]
    external_inputs: frozenset[str]


def _system_wiring_evidence(
    model: CompilationModel,
    context: _base._ExecutionContext,
    branch_context: _base.MachineBranchContext,
) -> _SystemWiringEvidence:
    declaration = context.function or branch_context.functions.get(context.entry)
    if context.system is None:
        return _SystemWiringEvidence(
            explicit=False,
            valid_context=declaration is not None,
            entry_inputs=frozenset(
                parameter.name for parameter in declaration.params
            ) if declaration is not None else frozenset(),
            external_inputs=frozenset(),
        )

    system = next((item for item in model.systems if item.name == context.system), None)
    if system is None or system.entry_name != context.entry or declaration is None:
        return _SystemWiringEvidence(True, False, frozenset(), frozenset())

    parameters = {parameter.name: parameter for parameter in declaration.params}
    input_ports = {
        port.name: port for port in system.ports if port.direction == "input"
    }
    edges = {(edge.source_name, edge.target_name) for edge in system.edges}
    entry_inputs = frozenset(
        name
        for name, port in input_ports.items()
        if (name, context.entry) in edges
        and name in parameters
        and port.type_text == _base._render_type(parameters[name].ty)
    )
    external_inputs = frozenset(
        name
        for name in input_ports
        if name in system.external_names
        and any(edge.source_name == name for edge in system.edges)
    )
    return _SystemWiringEvidence(True, True, entry_inputs, external_inputs)


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


def _source_state_value(
    context: _base.MachineBranchContext,
    source_state: str,
    parameter_name: str,
) -> Expr:
    arguments = tuple(
        NameExpr(source_state)
        if index == context.selector_index
        else FieldExpr(NameExpr(parameter_name), field.name)
        for index, field in enumerate(context.state_decl.fields)
    )
    return CallExpr(NameExpr(context.state_decl.name), arguments)


def _entry_values(
    execution_context: _base._ExecutionContext,
    evaluator: _SystemExecutionEvaluator,
) -> tuple[dict[str, Expr], dict[str, Expr]]:
    declaration = execution_context.function or evaluator._context.functions.get(
        execution_context.entry
    )
    if declaration is None:
        return {}, {}
    symbolic = {parameter.name: NameExpr(parameter.name) for parameter in declaration.params}
    concrete = dict(symbolic)
    state_type = evaluator._context.machine.state_param.ty
    state_name = evaluator._context.machine.state_param.name
    # Identify the current state by the Machine parameter name. Other parameters
    # may intentionally carry previous, comparison, or saved states of the same type.
    selected = next(
        (
            parameter
            for parameter in declaration.params
            if parameter.name == state_name and parameter.ty == state_type
        ),
        None,
    )
    # Keep symbolic values as provenance witnesses. Only the explicitly named
    # current-state parameter is specialized for source-state evaluation/rendering.
    if selected is not None:
        concrete[selected.name] = _source_state_value(
            evaluator._context,
            evaluator.source_state,
            selected.name,
        )
    return symbolic, concrete


def _machine_next_arguments(context: _base.MachineBranchContext) -> tuple[Expr, ...]:
    expression = unwrap_expr(context.machine.next_expr)
    if (
        isinstance(expression, CallExpr)
        and isinstance(expression.callee, NameExpr)
        and expression.callee.name == context.next_function
    ):
        return expression.args
    return ()


def _state_specialization_proof(
    context: _base._ExecutionContext,
    branch_context: _base.MachineBranchContext,
    wiring: _SystemWiringEvidence,
) -> tuple[bool, str]:
    declaration = context.function or branch_context.functions.get(context.entry)
    if declaration is None:
        return False, "System entry declaration is unavailable"

    state_type = branch_context.machine.state_param.ty
    expected_name = branch_context.machine.state_param.name
    state_parameters = [
        parameter for parameter in declaration.params if parameter.ty == state_type
    ]
    parameter = next(
        (item for item in state_parameters if item.name == expected_name),
        None,
    )
    # A state-typed parameter under another name is not evidence for the Machine
    # current state. An entry with no state-typed parameter is checked later by
    # transition-call argument provenance instead of state specialization.
    if parameter is None:
        if state_parameters:
            return False, "entry state parameter does not match the Machine state parameter"
        return True, ""
    if not wiring.explicit:
        return False, "implicit caller has no explicit System state-input wiring"
    if not wiring.valid_context:
        return False, "System entry does not match the execution context"
    if expected_name not in wiring.entry_inputs:
        return False, "current Machine state is not proven by System input wiring"
    return True, ""


def _local_input_sources(
    context: _base._ExecutionContext,
) -> dict[str, Expr]:
    if context.block is None:
        return {}
    sources: dict[str, Expr] = {}
    for binding in context.block.bindings:
        if not binding.name or binding.kind == "conditional":
            continue
        try:
            expression = parse_expr(binding.source)
        except Exception:
            continue
        sources[binding.name] = substitute_expr(expression, sources)
    return sources


def _blocked_binding(
    binding: Mapping[str, object],
    *,
    reason: str,
    state_input_unproven: bool,
) -> dict[str, object]:
    result = deepcopy(dict(binding))
    result["status"] = "unresolved"
    result["action"] = None
    result["action_invocations"] = []
    result["effect_invocations"] = []
    if state_input_unproven:
        result["state_specialization"] = {
            "status": "unproven",
            "reason": reason,
        }
    cases: list[dict[str, object]] = []
    for original in result.get("action_cases", []):
        if not isinstance(original, Mapping):
            continue
        case = deepcopy(dict(original))
        case["status"] = "unresolved"
        case["action"] = None
        case["action_invocations"] = []
        case["effect_invocations"] = []
        cases.append(case)
    result["action_cases"] = cases
    for key in ("execution_flow", "dataflow"):
        value = result.get(key)
        if isinstance(value, Mapping):
            record = deepcopy(dict(value))
            record["status"] = "unresolved"
            result[key] = record
    return result


class _SystemExecutionEvaluator(_base._SystemExecutionEvaluator):
    """Path evaluator with feasible paths, source specialization, and `?` flow."""

    def __init__(
        self,
        *,
        branch_context: _base.MachineBranchContext,
        externs: Mapping[str, ExternDecl],
        aliases: Mapping[str, TypeRef],
        branch_value: Expr,
        source_state: str,
        wiring: _SystemWiringEvidence,
        local_input_sources: Mapping[str, Expr],
    ) -> None:
        super().__init__(
            branch_context=branch_context,
            externs=externs,
            aliases=aliases,
            branch_value=branch_value,
        )
        self.source_state = source_state
        self.wiring = wiring
        self.local_input_sources = dict(local_input_sources)
        self.expected_transition_arguments = _machine_next_arguments(branch_context)
        self.machine_input_names = frozenset(
            parameter.name for parameter in branch_context.machine.input_params
        )
        self.transition_argument_mismatch = False

    def _input_roots(
        self,
        expression: Expr,
        *,
        visited_names: frozenset[str] = frozenset(),
    ) -> frozenset[tuple[str, str]] | None:
        expression = _inline_unguarded(expression, self._context.functions)
        if isinstance(expression, NameExpr):
            if expression.name in visited_names:
                return None
            local_source = self.local_input_sources.get(expression.name)
            if local_source is not None:
                return self._input_roots(
                    local_source,
                    visited_names=visited_names | {expression.name},
                )
            if (
                expression.name in self.machine_input_names
                or expression.name in self.wiring.entry_inputs
            ):
                return frozenset({("entry", expression.name)})
            return frozenset()
        if isinstance(expression, FieldExpr):
            return self._input_roots(
                expression.base, visited_names=visited_names
            )
        if isinstance(expression, TryExpr):
            return self._input_roots(
                expression.expr, visited_names=visited_names
            )
        if not isinstance(expression, CallExpr) or not isinstance(
            expression.callee, NameExpr
        ):
            return None
        name = expression.callee.name
        if name in self._externs:
            return frozenset({("external", name)})
        if name not in self._context.products:
            return None
        roots: set[tuple[str, str]] = set()
        for argument in expression.args:
            argument_roots = self._input_roots(
                argument, visited_names=visited_names
            )
            if argument_roots is None:
                return None
            roots.update(argument_roots)
        return frozenset(roots)

    def _input_argument_is_proven(self, expression: Expr, expected_name: str) -> bool:
        roots = self._input_roots(expression)
        if not roots:
            return False
        for kind, name in roots:
            if kind == "entry":
                if name not in self.wiring.entry_inputs:
                    return False
                if name in self.machine_input_names and name != expected_name:
                    return False
                continue
            if kind == "external":
                if self.wiring.explicit and name not in self.wiring.external_inputs:
                    return False
                continue
            return False
        return True

    def _transition_arguments_are_proven(self, call: CallExpr) -> bool:
        if len(call.args) != len(self.expected_transition_arguments):
            return False
        state_name = self._context.machine.state_param.name
        for actual, expected in zip(
            call.args, self.expected_transition_arguments, strict=True
        ):
            if isinstance(expected, NameExpr) and expected.name == state_name:
                if actual != expected:
                    return False
                continue
            if isinstance(expected, NameExpr) and expected.name in self.machine_input_names:
                if not self._input_argument_is_proven(actual, expected.name):
                    return False
                continue
            if actual != expected:
                return False
        return True

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

    def _evaluate_pure_call(
        self,
        symbolic: CallExpr,
        concrete: CallExpr,
        site: _base._TraceSite,
        *,
        visited: frozenset[str],
        after_transition: bool,
        conditions: tuple[str, ...],
    ) -> tuple[_base._Case, ...]:
        argument_states: list[tuple[list[Expr], list[Expr], _base._Case]] = [
            (
                [],
                [],
                _base._Case(
                    _base._ExprPair(NameExpr("_"), NameExpr("_")),
                    conditions=conditions,
                ),
            )
        ]
        for symbolic_argument, concrete_argument in zip(
            symbolic.args,
            concrete.args,
            strict=False,
        ):
            next_states: list[tuple[list[Expr], list[Expr], _base._Case]] = []
            for symbolic_values, concrete_values, prefix in argument_states:
                if prefix.terminated:
                    next_states.append((symbolic_values, concrete_values, prefix))
                    continue
                cases = self.evaluate(
                    _base._ExprPair(symbolic_argument, concrete_argument),
                    site,
                    visited=visited,
                    after_transition=after_transition or prefix.transition_calls > 0,
                    conditions=prefix.conditions,
                )
                for case in cases:
                    combined = _base._with_prefix(prefix, case)
                    next_states.append(
                        (
                            [*symbolic_values, case.value.symbolic],
                            [*concrete_values, case.value.concrete],
                            combined,
                        )
                    )
            argument_states = next_states

        result: list[_base._Case] = []
        for symbolic_values, concrete_values, prefix in argument_states:
            if prefix.terminated:
                result.append(prefix)
                continue
            result.append(
                _base._Case(
                    _base._ExprPair(
                        CallExpr(symbolic.callee, tuple(symbolic_values)),
                        CallExpr(concrete.callee, tuple(concrete_values)),
                    ),
                    prefix.invocations,
                    prefix.unresolved,
                    prefix.transition_calls,
                    prefix.conditions,
                )
            )
        return _base._deduplicate_cases(result)

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
        if (
            isinstance(symbolic.callee, NameExpr)
            and isinstance(concrete.callee, NameExpr)
            and symbolic.callee.name == concrete.callee.name == self._context.next_function
            and not self._transition_arguments_are_proven(symbolic)
        ):
            self.transition_argument_mismatch = True
            opaque = NameExpr(_UNPROVEN_TRANSITION_VALUE_NAME)
            return (
                _base._Case(
                    _base._ExprPair(opaque, opaque),
                    unresolved=True,
                    transition_calls=1,
                    conditions=conditions,
                ),
            )
        if _is_success_value(symbolic) and _is_success_value(concrete):
            return (
                _base._Case(
                    _base._ExprPair(symbolic, concrete),
                    conditions=conditions,
                ),
            )
        if (
            isinstance(symbolic.callee, NameExpr)
            and isinstance(concrete.callee, NameExpr)
            and symbolic.callee.name == concrete.callee.name
            and (
                symbolic.callee.name in self._context.products
                or symbolic.callee.name in self._context.constants
            )
        ):
            return self._evaluate_pure_call(
                symbolic,
                concrete,
                site,
                visited=visited,
                after_transition=after_transition,
                conditions=conditions,
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
    symbolic_values, concrete_values = _entry_values(context, evaluator)
    states: list[_base._BlockState] = [
        _base._BlockState(symbolic_values, concrete_values)
    ]
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


def _evaluate_function(
    context: _base._ExecutionContext,
    evaluator: _SystemExecutionEvaluator,
) -> _base._ContextEvaluation:
    assert context.function is not None
    symbolic_values, concrete_values = _entry_values(context, evaluator)
    cases = evaluator._evaluate_function_decl(
        context.function,
        symbolic_values,
        concrete_values,
        _base._TraceSite(
            context.system,
            context.entry,
            context.function.line,
            (context.entry,),
        ),
        visited=frozenset({context.function.name}),
        after_transition=False,
        conditions=(),
    )
    return _base._ContextEvaluation(context, cases)


def _diagnostic(code: str, message: str, line: int) -> dict[str, object]:
    return {"severity": "warning", "code": code, "message": message, "line": line}


def attach_transition_system_execution_actions(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Attach only execution contexts proven to represent each machine edge."""

    result = deepcopy(machine_view)
    branch_context = build_machine_branch_context(model, str(result.get("name") or ""))
    if branch_context is None:
        return result
    functions = branch_context.functions
    contexts = _base._execution_contexts(model, functions)
    context_wiring = tuple(
        (
            context,
            _system_wiring_evidence(model, context, branch_context),
            _local_input_sources(context),
        )
        for context in contexts
    )
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
        # Failure before the machine result returns cannot execute caller-side actions.
        if transition.get("synthesized_failure"):
            transition["execution_action_bindings"] = []
            transition["execution_contexts"] = []
            transitions.append(transition)
            continue

        source_state = str(transition.get("source_state") or "")
        branch_value = branch_value_for_transition(
            branch_context,
            transition,
            branch_plan,
        )
        if branch_value is None or not source_state:
            transition["execution_action_bindings"] = []
            transition["execution_contexts"] = []
            transitions.append(transition)
            continue
        source = transition.get("source", {})
        line = int(source.get("line", 1)) if isinstance(source, Mapping) else 1
        bindings: list[dict[str, object]] = []
        for context, wiring, local_input_sources in context_wiring:
            evaluator = _SystemExecutionEvaluator(
                branch_context=branch_context,
                externs=externs,
                aliases=aliases,
                branch_value=branch_value,
                source_state=source_state,
                wiring=wiring,
                local_input_sources=local_input_sources,
            )
            evaluation = (
                _evaluate_block(context, evaluator)
                if context.block is not None
                else _evaluate_function(context, evaluator)
            )
            binding = _base._binding(evaluation)
            if binding is None:
                continue

            proof_blocked = False
            state_proven, proof_reason = _state_specialization_proof(
                context,
                branch_context,
                wiring,
            )
            if not state_proven:
                proof_blocked = True
                binding = _blocked_binding(
                    binding,
                    reason=proof_reason,
                    state_input_unproven=True,
                )
                _base._append_diagnostic_once(
                    diagnostics,
                    _diagnostic(
                        _UNPROVEN_STATE_INPUT_CODE,
                        (
                            f"system `{context.system}` entry `{context.entry}` cannot prove "
                            f"the represented machine call: {proof_reason}"
                        ),
                        line,
                    ),
                )
            elif (
                evaluator.transition_argument_mismatch
                and binding.get("status") != "multiple-transition-calls"
            ):
                proof_blocked = True
                proof_reason = (
                    f"call to `{branch_context.next_function}` does not preserve the "
                    "Machine next-expression arguments"
                )
                binding = _blocked_binding(
                    binding,
                    reason=proof_reason,
                    state_input_unproven=False,
                )
                _base._append_diagnostic_once(
                    diagnostics,
                    _diagnostic(
                        _UNPROVEN_TRANSITION_ARGUMENT_CODE,
                        (
                            f"system `{context.system}` entry `{context.entry}` cannot prove "
                            f"the represented machine call: {proof_reason}"
                        ),
                        line,
                    ),
                )

            bindings.append(binding)
            binding_count += 1
            status = binding.get("status")
            if binding.get("action") is None:
                actionless_count += 1
            if status == "conditional":
                conditional_count += 1
            elif status == "unresolved":
                unresolved_count += 1
                if not proof_blocked:
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

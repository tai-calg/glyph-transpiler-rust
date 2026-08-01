from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from ._transition_action_ir import (
    _RESULT_CONSUMER_PROVENANCE,
    _SEQUENCED_SYSTEM_PROVENANCE,
    _SYSTEM_EXECUTION_PROVENANCE,
    build_operation_action,
    renumber_invocations,
    text,
)
from ._transition_branch_semantics import (
    MachineBranchContext,
    simplify_expr,
    substitute_expr,
)
from ._transition_source_planning import semantic_truth_value
from .artifacts import CompilationModel
from .compiler import (
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    NameExpr,
    NumberExpr,
    TryExpr,
    TypeRef,
    UnaryExpr,
    parse_expr,
)
from .execution_ir import render_expr
from .function_blocks import FunctionBlockLowering


_UNRESOLVED_CODE = "STIR_SYSTEM_ACTION_UNRESOLVED"
_MULTIPLE_CALLS_CODE = "STIR_SYSTEM_ACTION_MULTIPLE_TRANSITION_CALLS"
_MARKER_NAME = "__glyph_transition_result__"
_MARKER = NameExpr(_MARKER_NAME)


@dataclass(frozen=True)
class _ExprPair:
    symbolic: Expr
    concrete: Expr


@dataclass(frozen=True)
class _TraceSite:
    system: str | None
    entry: str
    line: int
    path: tuple[str, ...]


@dataclass(frozen=True)
class _Case:
    value: _ExprPair
    invocations: tuple[dict[str, object], ...] = ()
    unresolved: bool = False
    transition_calls: int = 0
    conditions: tuple[str, ...] = ()
    terminated: bool = False
    termination: str | None = None


@dataclass(frozen=True)
class _ExecutionContext:
    system: str | None
    entry: str
    scope: str
    block: FunctionBlockLowering | None
    function: FunctionDecl | None


@dataclass(frozen=True)
class _ContextEvaluation:
    context: _ExecutionContext
    cases: tuple[_Case, ...]


@dataclass(frozen=True)
class _BlockState:
    symbolic_values: Mapping[str, Expr]
    concrete_values: Mapping[str, Expr]
    invocations: tuple[dict[str, object], ...] = ()
    unresolved: bool = False
    transition_calls: int = 0
    conditions: tuple[str, ...] = ()
    terminated: bool = False
    termination: str | None = None


def _contains_marker(expression: Expr) -> bool:
    if isinstance(expression, NameExpr):
        return expression.name == _MARKER_NAME
    if isinstance(expression, FieldExpr):
        return _contains_marker(expression.base)
    if isinstance(expression, UnaryExpr):
        return _contains_marker(expression.expr)
    if isinstance(expression, BinaryExpr):
        return _contains_marker(expression.left) or _contains_marker(expression.right)
    if isinstance(expression, CallExpr):
        return _contains_marker(expression.callee) or any(
            _contains_marker(argument) for argument in expression.args
        )
    if isinstance(expression, TryExpr):
        return _contains_marker(expression.expr)
    return False


def _resolve_alias(type_ref: TypeRef, aliases: Mapping[str, TypeRef]) -> TypeRef:
    current = type_ref
    seen: set[str] = set()
    while not current.args and current.name in aliases and current.name not in seen:
        seen.add(current.name)
        current = aliases[current.name]
    return current


def _render_type(type_ref: TypeRef) -> str:
    if not type_ref.args:
        return type_ref.name
    return f"{type_ref.name}<{','.join(_render_type(item) for item in type_ref.args)}>"


def _failure_type(type_ref: TypeRef, aliases: Mapping[str, TypeRef]) -> str | None:
    resolved = _resolve_alias(type_ref, aliases)
    if resolved.name == "R" and len(resolved.args) == 2:
        return _render_type(resolved.args[1])
    return None


def _condition_text(expression: Expr, context: MachineBranchContext) -> str:
    simplified = simplify_expr(
        expression,
        products=context.products,
        constants=context.constants,
    )
    return render_expr(simplified)


def _negated(condition: str) -> str:
    condition = condition.strip()
    if condition.startswith("!(") and condition.endswith(")"):
        return condition[2:-1]
    return f"!({condition})"


def _append_condition(conditions: Sequence[str], condition: str) -> tuple[str, ...]:
    cleaned = condition.strip()
    if not cleaned or cleaned == "true":
        return tuple(conditions)
    if cleaned in conditions:
        return tuple(conditions)
    return (*conditions, cleaned)


def _condition_display(conditions: Sequence[str]) -> str | None:
    values = [item.strip() for item in conditions if item.strip() and item.strip() != "true"]
    return " & ".join(values) or None


def _with_prefix(prefix: _Case, nested: _Case, *, value: _ExprPair | None = None) -> _Case:
    return _Case(
        value=value or nested.value,
        invocations=(*prefix.invocations, *nested.invocations),
        unresolved=prefix.unresolved or nested.unresolved,
        transition_calls=prefix.transition_calls + nested.transition_calls,
        conditions=nested.conditions,
        terminated=prefix.terminated or nested.terminated,
        termination=nested.termination or prefix.termination,
    )


def _case_key(case: _Case) -> tuple[object, ...]:
    return (
        _condition_display(case.conditions),
        tuple(
            (text(item.get("expression")), item.get("failure_type"))
            for item in case.invocations
        ),
        case.unresolved,
        case.transition_calls,
        case.terminated,
        case.termination,
        render_expr(case.value.symbolic),
        render_expr(case.value.concrete),
    )


def _deduplicate_cases(cases: Sequence[_Case]) -> tuple[_Case, ...]:
    result: list[_Case] = []
    seen: set[tuple[object, ...]] = set()
    for case in cases:
        key = _case_key(case)
        if key in seen:
            continue
        seen.add(key)
        result.append(case)
    return tuple(result)


def _blocked_condition_cases(cases: Sequence[_Case]) -> tuple[_Case, ...]:
    """Conservatively block guards whose evaluation performs transition flow."""

    if not any(
        case.unresolved
        or case.transition_calls > 0
        or bool(case.invocations)
        or case.terminated
        for case in cases
    ):
        return ()
    return tuple(
        _Case(
            _ExprPair(NameExpr("_"), NameExpr("_")),
            case.invocations,
            True,
            case.transition_calls,
            case.conditions,
            case.terminated,
            case.termination,
        )
        for case in cases
    )


class _SystemExecutionEvaluator:
    """Path-sensitive evaluator for one system execution context.

    It preserves every feasible ordered path, models short-circuit Boolean operators,
    and splits `?` into success continuation and failure early-return paths. External
    operations are admitted only after the represented machine transition has run.
    """

    def __init__(
        self,
        *,
        branch_context: MachineBranchContext,
        externs: Mapping[str, ExternDecl],
        aliases: Mapping[str, TypeRef],
        branch_value: Expr,
    ) -> None:
        self._context = branch_context
        self._externs = externs
        self._aliases = aliases
        self._branch_value = branch_value

    def evaluate(
        self,
        pair: _ExprPair,
        site: _TraceSite,
        *,
        visited: frozenset[str] = frozenset(),
        after_transition: bool = False,
        conditions: tuple[str, ...] = (),
    ) -> tuple[_Case, ...]:
        symbolic = pair.symbolic
        concrete = pair.concrete

        if isinstance(symbolic, (BoolExpr, NumberExpr, NameExpr)):
            return (_Case(pair, conditions=conditions),)

        if isinstance(symbolic, FieldExpr) and isinstance(concrete, FieldExpr):
            return tuple(
                _Case(
                    _ExprPair(
                        FieldExpr(case.value.symbolic, symbolic.field),
                        FieldExpr(case.value.concrete, concrete.field),
                    ),
                    case.invocations,
                    case.unresolved,
                    case.transition_calls,
                    case.conditions,
                    case.terminated,
                    case.termination,
                )
                for case in self.evaluate(
                    _ExprPair(symbolic.base, concrete.base),
                    site,
                    visited=visited,
                    after_transition=after_transition,
                    conditions=conditions,
                )
            )

        if isinstance(symbolic, TryExpr) and isinstance(concrete, TryExpr):
            inner_cases = self.evaluate(
                _ExprPair(symbolic.expr, concrete.expr),
                site,
                visited=visited,
                after_transition=after_transition,
                conditions=conditions,
            )
            result: list[_Case] = []
            for inner in inner_cases:
                if inner.terminated:
                    result.append(inner)
                    continue
                rendered = render_expr(inner.value.concrete)
                success_condition = _append_condition(
                    inner.conditions,
                    f"success({rendered})",
                )
                failure_condition = _append_condition(
                    inner.conditions,
                    f"failure({rendered})",
                )
                value = _ExprPair(
                    TryExpr(inner.value.symbolic),
                    TryExpr(inner.value.concrete),
                )
                result.append(
                    _Case(
                        value,
                        inner.invocations,
                        inner.unresolved,
                        inner.transition_calls,
                        success_condition,
                    )
                )
                result.append(
                    _Case(
                        value,
                        inner.invocations,
                        inner.unresolved,
                        inner.transition_calls,
                        failure_condition,
                        True,
                        "failure-return",
                    )
                )
            return _deduplicate_cases(result)

        if isinstance(symbolic, UnaryExpr) and isinstance(concrete, UnaryExpr):
            return tuple(
                _Case(
                    _ExprPair(
                        UnaryExpr(symbolic.op, case.value.symbolic),
                        UnaryExpr(concrete.op, case.value.concrete),
                    ),
                    case.invocations,
                    case.unresolved,
                    case.transition_calls,
                    case.conditions,
                    case.terminated,
                    case.termination,
                )
                for case in self.evaluate(
                    _ExprPair(symbolic.expr, concrete.expr),
                    site,
                    visited=visited,
                    after_transition=after_transition,
                    conditions=conditions,
                )
            )

        if isinstance(symbolic, BinaryExpr) and isinstance(concrete, BinaryExpr):
            if symbolic.op in {"&", "|"}:
                return self._evaluate_short_circuit(
                    symbolic,
                    concrete,
                    site,
                    visited=visited,
                    after_transition=after_transition,
                    conditions=conditions,
                )
            return self._evaluate_binary(
                symbolic,
                concrete,
                site,
                visited=visited,
                after_transition=after_transition,
                conditions=conditions,
            )

        if isinstance(symbolic, CallExpr) and isinstance(concrete, CallExpr):
            return self._evaluate_call(
                symbolic,
                concrete,
                site,
                visited=visited,
                after_transition=after_transition,
                conditions=conditions,
            )

        return (
            _Case(
                pair,
                unresolved=_contains_marker(symbolic) or after_transition,
                conditions=conditions,
            ),
        )

    def _evaluate_binary(
        self,
        symbolic: BinaryExpr,
        concrete: BinaryExpr,
        site: _TraceSite,
        *,
        visited: frozenset[str],
        after_transition: bool,
        conditions: tuple[str, ...],
    ) -> tuple[_Case, ...]:
        result: list[_Case] = []
        left_cases = self.evaluate(
            _ExprPair(symbolic.left, concrete.left),
            site,
            visited=visited,
            after_transition=after_transition,
            conditions=conditions,
        )
        for left in left_cases:
            if left.terminated:
                result.append(left)
                continue
            right_cases = self.evaluate(
                _ExprPair(symbolic.right, concrete.right),
                site,
                visited=visited,
                after_transition=after_transition or left.transition_calls > 0,
                conditions=left.conditions,
            )
            for right in right_cases:
                combined = _with_prefix(
                    left,
                    right,
                    value=_ExprPair(
                        BinaryExpr(symbolic.op, left.value.symbolic, right.value.symbolic),
                        BinaryExpr(concrete.op, left.value.concrete, right.value.concrete),
                    ),
                )
                result.append(combined)
        return _deduplicate_cases(result)

    def _evaluate_short_circuit(
        self,
        symbolic: BinaryExpr,
        concrete: BinaryExpr,
        site: _TraceSite,
        *,
        visited: frozenset[str],
        after_transition: bool,
        conditions: tuple[str, ...],
    ) -> tuple[_Case, ...]:
        result: list[_Case] = []
        left_cases = self.evaluate(
            _ExprPair(symbolic.left, concrete.left),
            site,
            visited=visited,
            after_transition=after_transition,
            conditions=conditions,
        )
        for left in left_cases:
            if left.terminated:
                result.append(left)
                continue
            truth = semantic_truth_value(left.value.concrete, context=self._context)
            left_text = _condition_text(left.value.concrete, self._context)
            execute_right = truth is True if symbolic.op == "&" else truth is False
            short_value = False if symbolic.op == "&" else True
            if truth is not None:
                if not execute_right:
                    result.append(
                        _Case(
                            _ExprPair(BoolExpr(short_value), BoolExpr(short_value)),
                            left.invocations,
                            left.unresolved,
                            left.transition_calls,
                            left.conditions,
                        )
                    )
                    continue
                right_cases = self.evaluate(
                    _ExprPair(symbolic.right, concrete.right),
                    site,
                    visited=visited,
                    after_transition=after_transition or left.transition_calls > 0,
                    conditions=left.conditions,
                )
                result.extend(_with_prefix(left, right) for right in right_cases)
                continue

            right_condition = left_text if symbolic.op == "&" else _negated(left_text)
            short_condition = _negated(left_text) if symbolic.op == "&" else left_text
            result.append(
                _Case(
                    _ExprPair(BoolExpr(short_value), BoolExpr(short_value)),
                    left.invocations,
                    left.unresolved,
                    left.transition_calls,
                    _append_condition(left.conditions, short_condition),
                )
            )
            right_cases = self.evaluate(
                _ExprPair(symbolic.right, concrete.right),
                site,
                visited=visited,
                after_transition=after_transition or left.transition_calls > 0,
                conditions=_append_condition(left.conditions, right_condition),
            )
            result.extend(_with_prefix(left, right) for right in right_cases)
        return _deduplicate_cases(result)

    def _evaluate_call(
        self,
        symbolic: CallExpr,
        concrete: CallExpr,
        site: _TraceSite,
        *,
        visited: frozenset[str],
        after_transition: bool,
        conditions: tuple[str, ...],
    ) -> tuple[_Case, ...]:
        argument_states: list[tuple[list[Expr], list[Expr], _Case]] = [
            ([], [], _Case(_ExprPair(NameExpr("_"), NameExpr("_")), conditions=conditions))
        ]
        for symbolic_argument, concrete_argument in zip(
            symbolic.args,
            concrete.args,
            strict=False,
        ):
            next_states: list[tuple[list[Expr], list[Expr], _Case]] = []
            for symbolic_values, concrete_values, prefix in argument_states:
                if prefix.terminated:
                    next_states.append((symbolic_values, concrete_values, prefix))
                    continue
                cases = self.evaluate(
                    _ExprPair(symbolic_argument, concrete_argument),
                    site,
                    visited=visited,
                    after_transition=after_transition or prefix.transition_calls > 0,
                    conditions=prefix.conditions,
                )
                for case in cases:
                    combined = _with_prefix(prefix, case)
                    next_states.append(
                        (
                            [*symbolic_values, case.value.symbolic],
                            [*concrete_values, case.value.concrete],
                            combined,
                        )
                    )
            argument_states = next_states

        result: list[_Case] = []
        for symbolic_values, concrete_values, prefix in argument_states:
            if prefix.terminated:
                result.append(prefix)
                continue
            symbolic_call = CallExpr(symbolic.callee, tuple(symbolic_values))
            concrete_call = CallExpr(concrete.callee, tuple(concrete_values))
            if not isinstance(symbolic.callee, NameExpr) or not isinstance(
                concrete.callee,
                NameExpr,
            ):
                result.append(
                    _Case(
                        _ExprPair(symbolic_call, concrete_call),
                        prefix.invocations,
                        prefix.unresolved or _contains_marker(symbolic_call) or after_transition,
                        prefix.transition_calls,
                        prefix.conditions,
                    )
                )
                continue

            name = symbolic.callee.name
            if name == self._context.next_function:
                result.append(
                    _Case(
                        _ExprPair(_MARKER, self._branch_value),
                        prefix.invocations,
                        prefix.unresolved,
                        prefix.transition_calls + 1,
                        prefix.conditions,
                    )
                )
                continue

            external = self._externs.get(name)
            if external is not None:
                invocations = list(prefix.invocations)
                result_dependent = _contains_marker(symbolic_call)
                sequenced_after_transition = after_transition or prefix.transition_calls > 0
                if result_dependent or sequenced_after_transition:
                    rendered = render_expr(
                        simplify_expr(
                            concrete_call,
                            products=self._context.products,
                            constants=self._context.constants,
                        )
                    )
                    invocations.append(
                        {
                            "operation": name,
                            "expression": rendered,
                            "failure_type": _failure_type(
                                external.return_type,
                                self._aliases,
                            ),
                            "sequence": 0,
                            "effectful": True,
                            "kind": "effect-invocation",
                            "provenance": (
                                _RESULT_CONSUMER_PROVENANCE
                                if result_dependent
                                else _SEQUENCED_SYSTEM_PROVENANCE
                            ),
                            "execution_relation": (
                                "result-dependency"
                                if result_dependent
                                else "post-transition-control"
                            ),
                            "scope": "system" if site.system else "implicit-caller",
                            "system": site.system,
                            "entry": site.entry,
                            "source": {"line": site.line, "column": 1},
                            "execution_path": [*site.path, name],
                            "dataflow_path": [*site.path, name] if result_dependent else [],
                        }
                    )
                result.append(
                    _Case(
                        _ExprPair(symbolic_call, concrete_call),
                        tuple(invocations),
                        prefix.unresolved,
                        prefix.transition_calls,
                        prefix.conditions,
                    )
                )
                continue

            function = self._context.functions.get(name)
            if function is None or name in visited or len(function.params) != len(symbolic_values):
                result.append(
                    _Case(
                        _ExprPair(symbolic_call, concrete_call),
                        prefix.invocations,
                        prefix.unresolved
                        or _contains_marker(symbolic_call)
                        or after_transition
                        or prefix.transition_calls > 0,
                        prefix.transition_calls,
                        prefix.conditions,
                    )
                )
                continue

            symbolic_map = {
                parameter.name: value
                for parameter, value in zip(function.params, symbolic_values, strict=True)
            }
            concrete_map = {
                parameter.name: value
                for parameter, value in zip(function.params, concrete_values, strict=True)
            }
            nested_site = _TraceSite(site.system, site.entry, site.line, (*site.path, name))
            nested_after = after_transition or prefix.transition_calls > 0
            nested_visited = visited | {name}
            nested_cases = self._evaluate_function_decl(
                function,
                symbolic_map,
                concrete_map,
                nested_site,
                visited=nested_visited,
                after_transition=nested_after,
                conditions=prefix.conditions,
            )
            result.extend(_with_prefix(prefix, nested) for nested in nested_cases)
        return _deduplicate_cases(result)

    def _evaluate_function_decl(
        self,
        function: FunctionDecl,
        symbolic_values: Mapping[str, Expr],
        concrete_values: Mapping[str, Expr],
        site: _TraceSite,
        *,
        visited: frozenset[str],
        after_transition: bool,
        conditions: tuple[str, ...],
    ) -> tuple[_Case, ...]:
        if function.expression is not None:
            return self.evaluate(
                _ExprPair(
                    substitute_expr(function.expression, symbolic_values),
                    substitute_expr(function.expression, concrete_values),
                ),
                site,
                visited=visited,
                after_transition=after_transition,
                conditions=conditions,
            )

        result: list[_Case] = []
        remaining = conditions
        for clause in function.guards:
            if clause.condition is None:
                result.extend(
                    self.evaluate(
                        _ExprPair(
                            substitute_expr(clause.value, symbolic_values),
                            substitute_expr(clause.value, concrete_values),
                        ),
                        site,
                        visited=visited,
                        after_transition=after_transition,
                        conditions=remaining,
                    )
                )
                return _deduplicate_cases(result)

            concrete_condition = substitute_expr(clause.condition, concrete_values)
            symbolic_condition = substitute_expr(clause.condition, symbolic_values)
            condition_cases = self.evaluate(
                _ExprPair(symbolic_condition, concrete_condition),
                site,
                visited=visited,
                after_transition=after_transition,
                conditions=remaining,
            )
            blocked_condition_cases = _blocked_condition_cases(condition_cases)
            if blocked_condition_cases:
                result.extend(blocked_condition_cases)
                return _deduplicate_cases(result)
            truth = semantic_truth_value(concrete_condition, context=self._context)
            if truth is False:
                continue
            condition = _condition_text(symbolic_condition, self._context)
            if truth is True:
                result.extend(
                    self.evaluate(
                        _ExprPair(
                            substitute_expr(clause.value, symbolic_values),
                            substitute_expr(clause.value, concrete_values),
                        ),
                        site,
                        visited=visited,
                        after_transition=after_transition,
                        conditions=remaining,
                    )
                )
                return _deduplicate_cases(result)
            result.extend(
                self.evaluate(
                    _ExprPair(
                        substitute_expr(clause.value, symbolic_values),
                        substitute_expr(clause.value, concrete_values),
                    ),
                    site,
                    visited=visited,
                    after_transition=after_transition,
                    conditions=_append_condition(remaining, condition),
                )
            )
            remaining = _append_condition(remaining, _negated(condition))
        if not result:
            return (
                _Case(
                    _ExprPair(NameExpr("_"), NameExpr("_")),
                    unresolved=True,
                    conditions=remaining,
                ),
            )
        return _deduplicate_cases(result)


def _conditional_clauses(source: str) -> tuple[tuple[str | None, str], ...] | None:
    result: list[tuple[str | None, str]] = []
    for original in source.splitlines():
        stripped = original.strip()
        if "=>" not in stripped:
            return None
        condition, value = stripped.split("=>", 1)
        condition = condition.strip()
        value = value.strip()
        if not value:
            return None
        result.append((None if condition == "_" else condition, value))
    return tuple(result)


def _evaluate_conditional_binding(
    source: str,
    state: _BlockState,
    evaluator: _SystemExecutionEvaluator,
    site: _TraceSite,
) -> tuple[_Case, ...]:
    clauses = _conditional_clauses(source)
    if clauses is None:
        return (
            _Case(
                _ExprPair(NameExpr("_"), NameExpr("_")),
                unresolved=True,
                conditions=state.conditions,
            ),
        )
    result: list[_Case] = []
    remaining = state.conditions
    for condition_source, value_source in clauses:
        if condition_source is None:
            try:
                value = parse_expr(value_source)
            except Exception:
                return (
                    _Case(
                        _ExprPair(NameExpr("_"), NameExpr("_")),
                        unresolved=True,
                        conditions=remaining,
                    ),
                )
            result.extend(
                evaluator.evaluate(
                    _ExprPair(
                        substitute_expr(value, state.symbolic_values),
                        substitute_expr(value, state.concrete_values),
                    ),
                    site,
                    after_transition=state.transition_calls > 0,
                    conditions=remaining,
                )
            )
            return _deduplicate_cases(result)
        try:
            parsed_condition = parse_expr(condition_source)
            concrete_condition = substitute_expr(parsed_condition, state.concrete_values)
            symbolic_condition = substitute_expr(parsed_condition, state.symbolic_values)
            value = parse_expr(value_source)
        except Exception:
            return (
                _Case(
                    _ExprPair(NameExpr("_"), NameExpr("_")),
                    unresolved=True,
                    conditions=remaining,
                ),
            )
        condition_cases = evaluator.evaluate(
            _ExprPair(symbolic_condition, concrete_condition),
            site,
            after_transition=state.transition_calls > 0,
            conditions=remaining,
        )
        blocked_condition_cases = _blocked_condition_cases(condition_cases)
        if blocked_condition_cases:
            return blocked_condition_cases
        truth = semantic_truth_value(concrete_condition, context=evaluator._context)
        if truth is False:
            continue
        condition = _condition_text(symbolic_condition, evaluator._context)
        if truth is True:
            result.extend(
                evaluator.evaluate(
                    _ExprPair(
                        substitute_expr(value, state.symbolic_values),
                        substitute_expr(value, state.concrete_values),
                    ),
                    site,
                    after_transition=state.transition_calls > 0,
                    conditions=remaining,
                )
            )
            return _deduplicate_cases(result)
        result.extend(
            evaluator.evaluate(
                _ExprPair(
                    substitute_expr(value, state.symbolic_values),
                    substitute_expr(value, state.concrete_values),
                ),
                site,
                after_transition=state.transition_calls > 0,
                conditions=_append_condition(remaining, condition),
            )
        )
        remaining = _append_condition(remaining, _negated(condition))
    return _deduplicate_cases(result)








def _execution_contexts(
    model: CompilationModel,
    functions: Mapping[str, FunctionDecl],
) -> tuple[_ExecutionContext, ...]:
    blocks = {item.name: item for item in model.blocks}
    if model.systems:
        return tuple(
            _ExecutionContext(
                system=system.name,
                entry=system.entry_name,
                scope="system",
                block=blocks.get(system.entry_name),
                function=functions.get(system.entry_name),
            )
            for system in model.systems
            if blocks.get(system.entry_name) is not None
            or functions.get(system.entry_name) is not None
        )
    names = sorted(set(blocks) | set(functions))
    return tuple(
        _ExecutionContext(
            system=None,
            entry=name,
            scope="implicit-caller",
            block=blocks.get(name),
            function=functions.get(name),
        )
        for name in names
    )




def _append_diagnostic_once(
    diagnostics: list[dict[str, object]],
    diagnostic: dict[str, object],
) -> None:
    key = (
        diagnostic.get("code"),
        diagnostic.get("line"),
        diagnostic.get("message"),
    )
    if any(
        (item.get("code"), item.get("line"), item.get("message")) == key
        for item in diagnostics
    ):
        return
    diagnostics.append(diagnostic)


def _invocation_key(invocations: Sequence[Mapping[str, object]]) -> tuple[tuple[str, object], ...]:
    return tuple(
        (text(item.get("expression")), item.get("failure_type"))
        for item in invocations
    )


def _case_record(case: _Case) -> dict[str, object]:
    invocations = renumber_invocations(case.invocations)
    action = build_operation_action(invocations)
    return {
        "condition": _condition_display(case.conditions),
        "status": "unresolved" if case.unresolved else "resolved",
        "outcome": case.termination or "success",
        "reaches_continuation": not case.terminated,
        "transition_call_count": case.transition_calls,
        "action": action,
        "action_invocations": invocations,
        "effect_invocations": [dict(item) for item in invocations],
    }


def _conditional_action(records: Sequence[Mapping[str, object]]) -> dict[str, object] | None:
    labels: list[str] = []
    effectful = False
    for record in records:
        condition = text(record.get("condition")) or "otherwise"
        action = record.get("action")
        action_text = (
            text(action.get("display"))
            if isinstance(action, Mapping)
            else ""
        )
        if action_text:
            effectful = True
        labels.append(f"[{condition}] {action_text or '∅'}")
    if not labels:
        return None
    display = " | ".join(labels)
    return {
        "display": display,
        "expression": display,
        "operation": None,
        "operations": [],
        "kind": "conditional-operation-cases",
        "effectful": effectful,
        "provenance": "transition-operation-invocation",
        "source": {"line": 1, "column": 1},
    }


def _binding(evaluation: _ContextEvaluation) -> dict[str, object] | None:
    relevant = [case for case in evaluation.cases if case.transition_calls > 0]
    if not relevant:
        return None
    multiple = any(case.transition_calls != 1 for case in relevant)
    unresolved = any(case.unresolved for case in relevant)
    records = [_case_record(case) for case in relevant]
    if multiple:
        status = "multiple-transition-calls"
    elif unresolved:
        status = "unresolved"
    elif len(records) > 1 or any(record.get("condition") for record in records):
        status = "conditional"
    else:
        status = "resolved"

    sequence_keys = {
        _invocation_key(record.get("action_invocations", []))
        for record in records
        if isinstance(record, Mapping)
    }
    common_sequence = len(sequence_keys) == 1 and not unresolved and not multiple
    representative_invocations = (
        list(records[0].get("action_invocations", []))
        if records and common_sequence
        else []
    )
    action = (
        None
        if unresolved or multiple
        else build_operation_action(representative_invocations)
        if common_sequence
        else _conditional_action(records)
    )
    if action is not None:
        action["scope"] = evaluation.context.scope
        action["system"] = evaluation.context.system
        action["entry"] = evaluation.context.entry

    all_invocations = [
        item
        for record in records
        for item in record.get("action_invocations", [])
        if isinstance(item, Mapping)
    ]
    result_dependent = sum(
        1 for item in all_invocations if item.get("execution_relation") == "result-dependency"
    )
    sequenced = sum(
        1
        for item in all_invocations
        if item.get("execution_relation") == "post-transition-control"
    )
    execution_flow = {
        "provenance": _SYSTEM_EXECUTION_PROVENANCE,
        "system": evaluation.context.system,
        "entry": evaluation.context.entry,
        "status": status,
        "result_dependent_count": result_dependent,
        "sequenced_operation_count": sequenced,
        "case_count": len(records),
        "path": [evaluation.context.entry],
    }
    return {
        "scope": evaluation.context.scope,
        "system": evaluation.context.system,
        "entry": evaluation.context.entry,
        "status": status,
        "transition_call_count": max(case.transition_calls for case in relevant),
        "action": action,
        "action_invocations": representative_invocations,
        "effect_invocations": [dict(item) for item in representative_invocations],
        "action_cases": records,
        "execution_flow": execution_flow,
        "dataflow": dict(execution_flow),
    }


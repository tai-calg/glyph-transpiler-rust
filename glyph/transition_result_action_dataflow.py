from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping, Sequence

from ._transition_action_ir import (
    _RESULT_CONSUMER_PROVENANCE,
    build_operation_action,
    renumber_invocations,
    text,
)
from ._transition_branch_semantics import (
    MachineBranchContext,
    branch_value_for_transition,
    build_machine_branch_context,
    simplify_expr,
    substitute_expr,
)
from ._transition_source_planning import (
    planned_source_branches,
    semantic_truth_value,
)
from .artifacts import CompilationModel
from .compiler import (
    AliasDecl,
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
class _Evaluation:
    value: _ExprPair
    invocations: tuple[dict[str, object], ...] = ()
    unresolved: bool = False
    transition_calls: int = 0


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
    invocations: tuple[dict[str, object], ...]
    unresolved: bool
    transition_calls: int


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


def _combine_results(
    value: _ExprPair,
    results: Sequence[_Evaluation],
    *,
    unresolved: bool = False,
) -> _Evaluation:
    return _Evaluation(
        value=value,
        invocations=tuple(
            invocation
            for result in results
            for invocation in result.invocations
        ),
        unresolved=unresolved or any(result.unresolved for result in results),
        transition_calls=sum(result.transition_calls for result in results),
    )


class _ExecutionEvaluator:
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
    ) -> _Evaluation:
        symbolic = pair.symbolic
        concrete = pair.concrete

        if isinstance(symbolic, (BoolExpr, NumberExpr, NameExpr)):
            return _Evaluation(pair)
        if isinstance(symbolic, FieldExpr) and isinstance(concrete, FieldExpr):
            base = self.evaluate(
                _ExprPair(symbolic.base, concrete.base),
                site,
                visited=visited,
            )
            return _combine_results(
                _ExprPair(
                    FieldExpr(base.value.symbolic, symbolic.field),
                    FieldExpr(base.value.concrete, concrete.field),
                ),
                (base,),
            )
        if isinstance(symbolic, TryExpr) and isinstance(concrete, TryExpr):
            inner = self.evaluate(
                _ExprPair(symbolic.expr, concrete.expr),
                site,
                visited=visited,
            )
            return _combine_results(
                _ExprPair(TryExpr(inner.value.symbolic), TryExpr(inner.value.concrete)),
                (inner,),
            )
        if isinstance(symbolic, UnaryExpr) and isinstance(concrete, UnaryExpr):
            inner = self.evaluate(
                _ExprPair(symbolic.expr, concrete.expr),
                site,
                visited=visited,
            )
            return _combine_results(
                _ExprPair(
                    UnaryExpr(symbolic.op, inner.value.symbolic),
                    UnaryExpr(concrete.op, inner.value.concrete),
                ),
                (inner,),
            )
        if isinstance(symbolic, BinaryExpr) and isinstance(concrete, BinaryExpr):
            left = self.evaluate(
                _ExprPair(symbolic.left, concrete.left),
                site,
                visited=visited,
            )
            right = self.evaluate(
                _ExprPair(symbolic.right, concrete.right),
                site,
                visited=visited,
            )
            return _combine_results(
                _ExprPair(
                    BinaryExpr(symbolic.op, left.value.symbolic, right.value.symbolic),
                    BinaryExpr(concrete.op, left.value.concrete, right.value.concrete),
                ),
                (left, right),
            )
        if not isinstance(symbolic, CallExpr) or not isinstance(concrete, CallExpr):
            return _Evaluation(pair, unresolved=_contains_marker(symbolic))

        callee_symbolic = symbolic.callee
        callee_concrete = concrete.callee
        arguments = [
            self.evaluate(
                _ExprPair(symbolic_argument, concrete_argument),
                site,
                visited=visited,
            )
            for symbolic_argument, concrete_argument in zip(
                symbolic.args,
                concrete.args,
                strict=False,
            )
        ]
        symbolic_call = CallExpr(
            callee_symbolic,
            tuple(item.value.symbolic for item in arguments),
        )
        concrete_call = CallExpr(
            callee_concrete,
            tuple(item.value.concrete for item in arguments),
        )
        base = _combine_results(_ExprPair(symbolic_call, concrete_call), arguments)

        if not isinstance(callee_symbolic, NameExpr) or not isinstance(
            callee_concrete,
            NameExpr,
        ):
            return _Evaluation(
                base.value,
                base.invocations,
                base.unresolved or _contains_marker(symbolic_call),
                base.transition_calls,
            )

        name = callee_symbolic.name
        if name == self._context.next_function:
            return _Evaluation(
                _ExprPair(_MARKER, self._branch_value),
                base.invocations,
                base.unresolved,
                base.transition_calls + 1,
            )

        external = self._externs.get(name)
        if external is not None:
            invocations = list(base.invocations)
            if _contains_marker(symbolic_call):
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
                        "provenance": _RESULT_CONSUMER_PROVENANCE,
                        "scope": "system" if site.system else "implicit-caller",
                        "system": site.system,
                        "entry": site.entry,
                        "source": {"line": site.line, "column": 1},
                        "dataflow_path": [*site.path, name],
                    }
                )
            return _Evaluation(
                base.value,
                tuple(invocations),
                base.unresolved,
                base.transition_calls,
            )

        function = self._context.functions.get(name)
        if function is None:
            return _Evaluation(
                base.value,
                base.invocations,
                base.unresolved or _contains_marker(symbolic_call),
                base.transition_calls,
            )
        if name in visited or len(function.params) != len(arguments):
            return _Evaluation(
                base.value,
                base.invocations,
                base.unresolved or _contains_marker(symbolic_call),
                base.transition_calls,
            )

        symbolic_values = {
            parameter.name: argument.value.symbolic
            for parameter, argument in zip(function.params, arguments, strict=True)
        }
        concrete_values = {
            parameter.name: argument.value.concrete
            for parameter, argument in zip(function.params, arguments, strict=True)
        }
        nested_site = _TraceSite(
            site.system,
            site.entry,
            site.line,
            (*site.path, name),
        )
        nested_visited = visited | {name}

        if function.expression is not None:
            nested = self.evaluate(
                _ExprPair(
                    substitute_expr(function.expression, symbolic_values),
                    substitute_expr(function.expression, concrete_values),
                ),
                nested_site,
                visited=nested_visited,
            )
            return _Evaluation(
                nested.value,
                (*base.invocations, *nested.invocations),
                base.unresolved or nested.unresolved,
                base.transition_calls + nested.transition_calls,
            )

        for clause in function.guards:
            if clause.condition is not None:
                condition = substitute_expr(clause.condition, concrete_values)
                condition_truth = semantic_truth_value(
                    condition,
                    context=self._context,
                )
                if condition_truth is False:
                    continue
                if condition_truth is None:
                    return _Evaluation(
                        base.value,
                        base.invocations,
                        base.unresolved or _contains_marker(symbolic_call),
                        base.transition_calls,
                    )
            nested = self.evaluate(
                _ExprPair(
                    substitute_expr(clause.value, symbolic_values),
                    substitute_expr(clause.value, concrete_values),
                ),
                nested_site,
                visited=nested_visited,
            )
            return _Evaluation(
                nested.value,
                (*base.invocations, *nested.invocations),
                base.unresolved or nested.unresolved,
                base.transition_calls + nested.transition_calls,
            )

        return _Evaluation(
            base.value,
            base.invocations,
            base.unresolved or _contains_marker(symbolic_call),
            base.transition_calls,
        )


def _parse_conditional_value(
    source: str,
    *,
    symbolic_values: Mapping[str, Expr],
    concrete_values: Mapping[str, Expr],
    evaluator: _ExecutionEvaluator,
    site: _TraceSite,
) -> _Evaluation:
    for original in source.splitlines():
        stripped = original.strip()
        if "=>" not in stripped:
            return _Evaluation(_ExprPair(NameExpr("_"), NameExpr("_")), unresolved=True)
        condition_source, value_source = stripped.split("=>", 1)
        condition_source = condition_source.strip()
        if condition_source != "_":
            try:
                condition = substitute_expr(
                    parse_expr(condition_source),
                    concrete_values,
                )
            except Exception:
                return _Evaluation(_ExprPair(NameExpr("_"), NameExpr("_")), unresolved=True)
            condition_truth = semantic_truth_value(
                condition,
                context=evaluator._context,
            )
            if condition_truth is False:
                continue
            if condition_truth is None:
                return _Evaluation(_ExprPair(NameExpr("_"), NameExpr("_")), unresolved=True)
        try:
            value = parse_expr(value_source.strip())
        except Exception:
            return _Evaluation(_ExprPair(NameExpr("_"), NameExpr("_")), unresolved=True)
        return evaluator.evaluate(
            _ExprPair(
                substitute_expr(value, symbolic_values),
                substitute_expr(value, concrete_values),
            ),
            site,
        )
    return _Evaluation(_ExprPair(NameExpr("_"), NameExpr("_")), unresolved=True)


def _evaluate_block(
    context: _ExecutionContext,
    evaluator: _ExecutionEvaluator,
) -> _ContextEvaluation:
    assert context.block is not None
    symbolic_values: dict[str, Expr] = {}
    concrete_values: dict[str, Expr] = {}
    invocations: list[dict[str, object]] = []
    unresolved = False
    transition_calls = 0
    path = (context.entry,)

    for binding in context.block.bindings:
        site = _TraceSite(
            context.system,
            context.entry,
            binding.line,
            path,
        )
        if binding.kind == "conditional":
            result = _parse_conditional_value(
                binding.source,
                symbolic_values=symbolic_values,
                concrete_values=concrete_values,
                evaluator=evaluator,
                site=site,
            )
        else:
            try:
                expression = parse_expr(binding.source)
            except Exception:
                unresolved = True
                continue
            result = evaluator.evaluate(
                _ExprPair(
                    substitute_expr(expression, symbolic_values),
                    substitute_expr(expression, concrete_values),
                ),
                site,
            )
        invocations.extend(result.invocations)
        unresolved = unresolved or result.unresolved
        transition_calls += result.transition_calls
        symbolic_values[binding.name] = result.value.symbolic
        concrete_values[binding.name] = result.value.concrete

    try:
        final_expression = parse_expr(context.block.final_source)
    except Exception:
        return _ContextEvaluation(
            context,
            tuple(invocations),
            True,
            transition_calls,
        )
    final = evaluator.evaluate(
        _ExprPair(
            substitute_expr(final_expression, symbolic_values),
            substitute_expr(final_expression, concrete_values),
        ),
        _TraceSite(
            context.system,
            context.entry,
            context.block.final_line,
            path,
        ),
    )
    invocations.extend(final.invocations)
    return _ContextEvaluation(
        context,
        tuple(invocations),
        unresolved or final.unresolved,
        transition_calls + final.transition_calls,
    )


def _evaluate_function(
    context: _ExecutionContext,
    evaluator: _ExecutionEvaluator,
) -> _ContextEvaluation:
    assert context.function is not None
    function = context.function
    identity = {parameter.name: NameExpr(parameter.name) for parameter in function.params}
    site = _TraceSite(
        context.system,
        context.entry,
        function.line,
        (context.entry,),
    )
    if function.expression is not None:
        result = evaluator.evaluate(
            _ExprPair(
                substitute_expr(function.expression, identity),
                substitute_expr(function.expression, identity),
            ),
            site,
            visited=frozenset({function.name}),
        )
        return _ContextEvaluation(
            context,
            result.invocations,
            result.unresolved,
            result.transition_calls,
        )

    for clause in function.guards:
        if clause.condition is not None:
            condition_truth = semantic_truth_value(
                clause.condition,
                context=evaluator._context,
            )
            if condition_truth is False:
                continue
            if condition_truth is None:
                return _ContextEvaluation(context, (), True, 0)
        result = evaluator.evaluate(
            _ExprPair(clause.value, clause.value),
            site,
            visited=frozenset({function.name}),
        )
        return _ContextEvaluation(
            context,
            result.invocations,
            result.unresolved,
            result.transition_calls,
        )
    return _ContextEvaluation(context, (), False, 0)


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


def _diagnostic(code: str, message: str, line: int) -> dict[str, object]:
    return {
        "severity": "warning",
        "code": code,
        "message": message,
        "line": line,
    }


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


def _binding(
    evaluation: _ContextEvaluation,
) -> dict[str, object] | None:
    invocations = renumber_invocations(evaluation.invocations)
    action = build_operation_action(invocations)
    if action is None:
        return None
    action["scope"] = evaluation.context.scope
    action["system"] = evaluation.context.system
    action["entry"] = evaluation.context.entry
    return {
        "scope": evaluation.context.scope,
        "system": evaluation.context.system,
        "entry": evaluation.context.entry,
        "action": action,
        "action_invocations": invocations,
        "effect_invocations": [dict(item) for item in invocations],
        "dataflow": {
            "provenance": _RESULT_CONSUMER_PROVENANCE,
            "system": evaluation.context.system,
            "entry": evaluation.context.entry,
            "path": [
                evaluation.context.entry,
                *[
                    text(item.get("operation"))
                    for item in invocations
                    if text(item.get("operation"))
                ],
            ],
        },
    }


def attach_transition_result_consumer_actions(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Attach system-entry operations without mutating intrinsic machine Action.

    Every declared system entry is evaluated independently. Calls to the machine
    next function are recognized in direct expressions, nested call arguments,
    immutable bindings, and recursively evaluated pure helpers. Divergent systems
    remain distinct bindings rather than being collapsed into an ambiguous machine
    Action.
    """

    result = deepcopy(machine_view)
    branch_context = build_machine_branch_context(
        model,
        str(result.get("name") or ""),
    )
    if branch_context is None:
        return result

    functions = branch_context.functions
    contexts = _execution_contexts(model, functions)
    externs = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, ExternDecl)
    }
    aliases = {
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
    unresolved_count = 0
    multiple_call_count = 0

    for original in result.get("transitions", []):
        transition = dict(original)
        branch_value = branch_value_for_transition(
            branch_context,
            transition,
            branch_plan,
        )
        if branch_value is None:
            transition["execution_action_bindings"] = []
            transitions.append(transition)
            continue

        source = transition.get("source", {})
        line = int(source.get("line", 1)) if isinstance(source, Mapping) else 1
        bindings: list[dict[str, object]] = []
        for context in contexts:
            evaluator = _ExecutionEvaluator(
                branch_context=branch_context,
                externs=externs,
                aliases=aliases,
                branch_value=branch_value,
            )
            evaluation = (
                _evaluate_block(context, evaluator)
                if context.block is not None
                else _evaluate_function(context, evaluator)
            )
            if evaluation.transition_calls == 0:
                continue
            context_name = (
                f"system `{context.system}` entry `{context.entry}`"
                if context.system
                else f"implicit caller `{context.entry}`"
            )
            if evaluation.transition_calls != 1:
                multiple_call_count += 1
                _append_diagnostic_once(
                    diagnostics,
                    _diagnostic(
                        _MULTIPLE_CALLS_CODE,
                        (
                            f"{context_name} invokes `{branch_context.next_function}` "
                            f"{evaluation.transition_calls} times; a single machine edge "
                            "cannot own that composed execution Action"
                        ),
                        line,
                    ),
                )
                continue
            if evaluation.unresolved:
                unresolved_count += 1
                _append_diagnostic_once(
                    diagnostics,
                    _diagnostic(
                        _UNRESOLVED_CODE,
                        (
                            f"{context_name} consumes `{branch_context.next_function}` "
                            "through a path whose operation cannot be proven"
                        ),
                        line,
                    ),
                )
                continue
            binding = _binding(evaluation)
            if binding is not None:
                bindings.append(binding)
                binding_count += 1

        transition["execution_action_bindings"] = bindings
        transitions.append(transition)

    analysis = dict(result.get("analysis", {}))
    analysis.update(
        {
            "transition_result_consumer_action_version": 2,
            "execution_action_context_count": len(contexts),
            "execution_action_binding_count": binding_count,
            "execution_action_unresolved_count": unresolved_count,
            "execution_action_multiple_transition_call_count": multiple_call_count,
        }
    )
    result["transitions"] = transitions
    result["diagnostics"] = diagnostics
    result["analysis"] = analysis
    return result


__all__ = ["attach_transition_result_consumer_actions"]

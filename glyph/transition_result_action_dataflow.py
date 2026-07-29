from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping, Sequence

from ._transition_branch_semantics import (
    MachineBranchContext,
    branch_value_for_transition,
    build_machine_branch_context,
    simplify_expr,
    substitute_expr,
    truth_value,
    unwrap_expr,
)
from .artifacts import CompilationModel
from .compiler import (
    AliasDecl,
    BinaryExpr,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    NameExpr,
    TryExpr,
    TypeRef,
    UnaryExpr,
    parse_expr,
)
from .execution_ir import render_expr
from .function_blocks import FunctionBlockLowering


_ACTION_PROVENANCE = "transition-operation-invocation"
_CONSUMER_PROVENANCE = "transition-result-consumer"
_AMBIGUOUS_CODE = "STIR_ACTION_RESULT_CONSUMER_AMBIGUOUS"
_UNRESOLVED_CODE = "STIR_ACTION_RESULT_CONSUMER_UNRESOLVED"
_MARKER_NAME = "__glyph_transition_result__"
_MARKER = NameExpr(_MARKER_NAME)


@dataclass(frozen=True)
class _ExprPair:
    symbolic: Expr
    concrete: Expr


@dataclass(frozen=True)
class _ConsumerContext:
    caller: str
    binding_name: str
    binding_index: int
    block: FunctionBlockLowering


@dataclass(frozen=True)
class _TraceSite:
    caller: str
    line: int
    path: tuple[str, ...]


@dataclass(frozen=True)
class _TraceResult:
    invocations: tuple[dict[str, object], ...]
    unresolved: bool = False


@dataclass(frozen=True)
class _ContextTrace:
    context: _ConsumerContext
    invocations: tuple[dict[str, object], ...]
    unresolved: bool


def _text(value: object) -> str:
    return str(value or "").strip()


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


class _OperationTracer:
    def __init__(
        self,
        *,
        branch_context: MachineBranchContext,
        externs: Mapping[str, ExternDecl],
        aliases: Mapping[str, TypeRef],
    ) -> None:
        self._context = branch_context
        self._externs = externs
        self._aliases = aliases

    def trace(
        self,
        pair: _ExprPair,
        site: _TraceSite,
        *,
        visited: frozenset[str] = frozenset(),
    ) -> _TraceResult:
        symbolic = pair.symbolic
        concrete = pair.concrete

        if isinstance(symbolic, FieldExpr) and isinstance(concrete, FieldExpr):
            return self.trace(
                _ExprPair(symbolic.base, concrete.base),
                site,
                visited=visited,
            )
        if isinstance(symbolic, TryExpr) and isinstance(concrete, TryExpr):
            return self.trace(
                _ExprPair(symbolic.expr, concrete.expr),
                site,
                visited=visited,
            )
        if isinstance(symbolic, UnaryExpr) and isinstance(concrete, UnaryExpr):
            return self.trace(
                _ExprPair(symbolic.expr, concrete.expr),
                site,
                visited=visited,
            )
        if isinstance(symbolic, BinaryExpr) and isinstance(concrete, BinaryExpr):
            left = self.trace(
                _ExprPair(symbolic.left, concrete.left),
                site,
                visited=visited,
            )
            right = self.trace(
                _ExprPair(symbolic.right, concrete.right),
                site,
                visited=visited,
            )
            return _TraceResult(
                (*left.invocations, *right.invocations),
                left.unresolved or right.unresolved,
            )
        if not isinstance(symbolic, CallExpr) or not isinstance(concrete, CallExpr):
            return _TraceResult(())

        nested: list[dict[str, object]] = []
        unresolved = False
        for symbolic_argument, concrete_argument in zip(
            symbolic.args,
            concrete.args,
            strict=False,
        ):
            result = self.trace(
                _ExprPair(symbolic_argument, concrete_argument),
                site,
                visited=visited,
            )
            nested.extend(result.invocations)
            unresolved = unresolved or result.unresolved

        if not isinstance(symbolic.callee, NameExpr) or not isinstance(
            concrete.callee,
            NameExpr,
        ):
            return _TraceResult(
                tuple(nested),
                unresolved or _contains_marker(symbolic),
            )

        name = symbolic.callee.name
        external = self._externs.get(name)
        if external is not None:
            if not _contains_marker(symbolic):
                return _TraceResult(tuple(nested), unresolved)
            rendered = render_expr(
                simplify_expr(
                    concrete,
                    products=self._context.products,
                    constants=self._context.constants,
                )
            )
            nested.append(
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
                    "provenance": _CONSUMER_PROVENANCE,
                    "source": {"line": site.line, "column": 1},
                    "caller": site.caller,
                    "dataflow_path": [*site.path, name],
                }
            )
            return _TraceResult(tuple(nested), unresolved)

        function = self._context.functions.get(name)
        if function is None:
            return _TraceResult(tuple(nested), unresolved)
        if name in visited or len(function.params) != len(symbolic.args):
            return _TraceResult(
                tuple(nested),
                unresolved or _contains_marker(symbolic),
            )

        symbolic_values = {
            parameter.name: argument
            for parameter, argument in zip(
                function.params,
                symbolic.args,
                strict=True,
            )
        }
        concrete_values = {
            parameter.name: argument
            for parameter, argument in zip(
                function.params,
                concrete.args,
                strict=True,
            )
        }
        next_site = _TraceSite(site.caller, site.line, (*site.path, name))
        next_visited = visited | {name}

        if function.expression is not None:
            result = self.trace(
                _ExprPair(
                    substitute_expr(function.expression, symbolic_values),
                    substitute_expr(function.expression, concrete_values),
                ),
                next_site,
                visited=next_visited,
            )
            return _TraceResult(
                (*nested, *result.invocations),
                unresolved or result.unresolved,
            )

        for clause in function.guards:
            if clause.condition is None:
                selected = _ExprPair(
                    substitute_expr(clause.value, symbolic_values),
                    substitute_expr(clause.value, concrete_values),
                )
                result = self.trace(
                    selected,
                    next_site,
                    visited=next_visited,
                )
                return _TraceResult(
                    (*nested, *result.invocations),
                    unresolved or result.unresolved,
                )

            condition = substitute_expr(clause.condition, concrete_values)
            condition_truth = truth_value(
                condition,
                products=self._context.products,
                constants=self._context.constants,
            )
            if condition_truth is False:
                continue
            if condition_truth is None:
                return _TraceResult(
                    tuple(nested),
                    unresolved or _contains_marker(symbolic),
                )
            result = self.trace(
                _ExprPair(
                    substitute_expr(clause.value, symbolic_values),
                    substitute_expr(clause.value, concrete_values),
                ),
                next_site,
                visited=next_visited,
            )
            return _TraceResult(
                (*nested, *result.invocations),
                unresolved or result.unresolved,
            )

        return _TraceResult(
            tuple(nested),
            unresolved or _contains_marker(symbolic),
        )


def _direct_call_name(expression: Expr) -> str | None:
    value = unwrap_expr(expression)
    if isinstance(value, CallExpr) and isinstance(value.callee, NameExpr):
        return value.callee.name
    return None


def _consumer_contexts(
    model: CompilationModel,
    next_function: str,
) -> tuple[_ConsumerContext, ...]:
    contexts: list[_ConsumerContext] = []
    for block in model.blocks:
        matches: list[tuple[int, object]] = []
        for index, binding in enumerate(block.bindings):
            if binding.kind != "expression":
                continue
            try:
                expression = parse_expr(binding.source)
            except Exception:
                continue
            if _direct_call_name(expression) == next_function:
                matches.append((index, binding))
        if len(matches) != 1:
            continue
        index, binding = matches[0]
        contexts.append(
            _ConsumerContext(
                caller=block.name,
                binding_name=binding.name,
                binding_index=index,
                block=block,
            )
        )

    entries = {system.entry_name for system in model.systems}
    entry_contexts = tuple(item for item in contexts if item.caller in entries)
    return entry_contexts or tuple(contexts)


def _conditional_pair(
    source: str,
    *,
    symbolic_values: Mapping[str, Expr],
    concrete_values: Mapping[str, Expr],
    branch_context: MachineBranchContext,
) -> tuple[_ExprPair | None, bool]:
    clauses: list[tuple[str | None, str]] = []
    for original in source.splitlines():
        stripped = original.strip()
        if "=>" not in stripped:
            return None, True
        condition, value = stripped.split("=>", 1)
        clauses.append(
            (
                None if condition.strip() == "_" else condition.strip(),
                value.strip(),
            )
        )

    for condition_source, value_source in clauses:
        if condition_source is not None:
            try:
                condition = substitute_expr(
                    parse_expr(condition_source),
                    concrete_values,
                )
            except Exception:
                return None, True
            condition_truth = truth_value(
                condition,
                products=branch_context.products,
                constants=branch_context.constants,
            )
            if condition_truth is False:
                continue
            if condition_truth is None:
                return None, True
        try:
            value = parse_expr(value_source)
        except Exception:
            return None, True
        return _ExprPair(
            substitute_expr(value, symbolic_values),
            substitute_expr(value, concrete_values),
        ), False
    return None, True


def _evaluate_context(
    context: _ConsumerContext,
    *,
    branch_value: Expr,
    tracer: _OperationTracer,
    branch_context: MachineBranchContext,
) -> _ContextTrace:
    symbolic_values: dict[str, Expr] = {context.binding_name: _MARKER}
    concrete_values: dict[str, Expr] = {context.binding_name: branch_value}
    invocations: list[dict[str, object]] = []
    unresolved = False
    path = (
        branch_context.next_function,
        f"{context.caller}.{context.binding_name}",
    )

    for binding in context.block.bindings[context.binding_index + 1 :]:
        if binding.kind == "conditional":
            pair, failed = _conditional_pair(
                binding.source,
                symbolic_values=symbolic_values,
                concrete_values=concrete_values,
                branch_context=branch_context,
            )
            if pair is None:
                unresolved = unresolved or failed
                continue
        else:
            try:
                expression = parse_expr(binding.source)
            except Exception:
                unresolved = True
                continue
            pair = _ExprPair(
                substitute_expr(expression, symbolic_values),
                substitute_expr(expression, concrete_values),
            )

        traced = tracer.trace(
            pair,
            _TraceSite(context.caller, binding.line, path),
        )
        invocations.extend(traced.invocations)
        unresolved = unresolved or traced.unresolved
        symbolic_values[binding.name] = pair.symbolic
        concrete_values[binding.name] = pair.concrete

    try:
        final_expression = parse_expr(context.block.final_source)
    except Exception:
        return _ContextTrace(context, tuple(invocations), True)
    final_pair = _ExprPair(
        substitute_expr(final_expression, symbolic_values),
        substitute_expr(final_expression, concrete_values),
    )
    traced = tracer.trace(
        final_pair,
        _TraceSite(context.caller, context.block.final_line, path),
    )
    invocations.extend(traced.invocations)
    return _ContextTrace(
        context,
        tuple(invocations),
        unresolved or traced.unresolved,
    )


def _action_value(
    invocations: Sequence[Mapping[str, object]],
) -> dict[str, object] | None:
    expressions = [_text(item.get("expression")) for item in invocations]
    expressions = [item for item in expressions if item]
    if not expressions:
        return None
    operations = [_text(item.get("operation")) for item in invocations]
    operations = [item for item in operations if item]
    display = "; ".join(expressions)
    source = invocations[0].get("source", {"line": 1, "column": 1})
    return {
        "display": display,
        "expression": display,
        "operation": operations[0] if len(operations) == 1 else None,
        "operations": operations,
        "kind": (
            "operation-invocation"
            if len(expressions) == 1
            else "operation-sequence"
        ),
        "effectful": True,
        "provenance": _ACTION_PROVENANCE,
        "source": dict(source) if isinstance(source, Mapping) else source,
    }


def _diagnostic(code: str, message: str, line: int) -> dict[str, object]:
    return {
        "severity": "warning",
        "code": code,
        "message": message,
        "line": line,
    }


def _sequence_key(
    invocations: Sequence[Mapping[str, object]],
) -> tuple[tuple[str, str | None], ...]:
    return tuple(
        (_text(item.get("expression")), item.get("failure_type"))
        for item in invocations
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


def attach_transition_result_consumer_actions(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Attach only caller operations proven to consume a transition result."""

    result = deepcopy(machine_view)
    branch_context = build_machine_branch_context(
        model,
        str(result.get("name") or ""),
    )
    if branch_context is None:
        return result

    contexts = _consumer_contexts(model, branch_context.next_function)
    analysis = dict(result.get("analysis", {}))
    analysis["transition_result_consumer_action_version"] = 1
    analysis["transition_result_consumer_context_count"] = len(contexts)
    if not contexts:
        result["analysis"] = analysis
        return result

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
    tracer = _OperationTracer(
        branch_context=branch_context,
        externs=externs,
        aliases=aliases,
    )
    state_names = [str(item.get("name", "")) for item in result.get("states", [])]
    unreachable_lines = frozenset(map(int, result.get("unreachable_branches", [])))
    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
    transitions: list[dict[str, object]] = []
    consumer_action_count = 0
    ambiguous_count = 0
    unresolved_count = 0

    for original in result.get("transitions", []):
        transition = dict(original)
        branch_value = branch_value_for_transition(
            branch_context,
            transition,
            state_names,
            unreachable_lines=unreachable_lines,
        )
        if branch_value is None:
            transitions.append(transition)
            continue

        evaluations = [
            _evaluate_context(
                context,
                branch_value=branch_value,
                tracer=tracer,
                branch_context=branch_context,
            )
            for context in contexts
        ]
        source = transition.get("source", {})
        line = int(source.get("line", 1)) if isinstance(source, Mapping) else 1
        if any(item.unresolved for item in evaluations):
            unresolved_count += 1
            _append_diagnostic_once(
                diagnostics,
                _diagnostic(
                    _UNRESOLVED_CODE,
                    (
                        f"transition result from `{branch_context.next_function}` reaches "
                        "a caller path whose operation cannot be proven; Action remains unchanged"
                    ),
                    line,
                ),
            )
            transitions.append(transition)
            continue

        by_key: dict[tuple[tuple[str, str | None], ...], _ContextTrace] = {}
        for evaluation in evaluations:
            by_key.setdefault(_sequence_key(evaluation.invocations), evaluation)
        if len(by_key) > 1:
            ambiguous_count += 1
            _append_diagnostic_once(
                diagnostics,
                _diagnostic(
                    _AMBIGUOUS_CODE,
                    (
                        f"transition result from `{branch_context.next_function}` has multiple "
                        "caller operation sequences; no downstream Action is invented"
                    ),
                    line,
                ),
            )
            transitions.append(transition)
            continue

        selected = next(iter(by_key.values()))
        downstream = [dict(item) for item in selected.invocations]
        if not downstream:
            transitions.append(transition)
            continue

        existing = [
            dict(item)
            for item in transition.get("action_invocations", [])
            if isinstance(item, Mapping)
        ]
        combined = [*existing, *downstream]
        for sequence, invocation in enumerate(combined, start=1):
            invocation["sequence"] = sequence
        transition["action_invocations"] = combined

        effects = [
            dict(item)
            for item in transition.get("effect_invocations", [])
            if isinstance(item, Mapping)
        ]
        effect_keys = {
            (_text(item.get("expression")), item.get("failure_type"))
            for item in effects
        }
        for invocation in downstream:
            key = (
                _text(invocation.get("expression")),
                invocation.get("failure_type"),
            )
            if key not in effect_keys:
                effects.append(dict(invocation))
                effect_keys.add(key)
        for sequence, invocation in enumerate(effects, start=1):
            invocation["sequence"] = sequence
        transition["effect_invocations"] = effects
        transition["action"] = _action_value(combined)
        transition["action_result_dataflow"] = {
            "provenance": _CONSUMER_PROVENANCE,
            "caller": selected.context.caller,
            "binding": selected.context.binding_name,
            "path": [
                branch_context.next_function,
                f"{selected.context.caller}.{selected.context.binding_name}",
                *[
                    _text(item.get("operation"))
                    for item in downstream
                    if _text(item.get("operation"))
                ],
            ],
        }
        consumer_action_count += len(downstream)
        transitions.append(transition)

    analysis.update(
        {
            "transition_result_consumer_action_count": consumer_action_count,
            "transition_result_consumer_ambiguous_count": ambiguous_count,
            "transition_result_consumer_unresolved_count": unresolved_count,
        }
    )
    result["transitions"] = transitions
    result["diagnostics"] = diagnostics
    result["analysis"] = analysis
    return result


__all__ = ["attach_transition_result_consumer_actions"]

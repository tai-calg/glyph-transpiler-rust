from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping, Sequence

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
    ProductDecl,
    SumDecl,
    TryExpr,
    TypeRef,
    UnaryExpr,
    parse_expr,
)
from .execution_ir import render_expr
from .state_transition_compiler import _root_branches

if TYPE_CHECKING:
    from .artifacts import CompilationModel


ACTION_PROVENANCE = "transition-operation-invocation"
CONSUMER_PROVENANCE = "transition-result-consumer"
_AMBIGUOUS_CODE = "STIR_ACTION_RESULT_CONSUMER_AMBIGUOUS"
_UNRESOLVED_CODE = "STIR_ACTION_RESULT_CONSUMER_UNRESOLVED"
_MARKER_NAME = "__glyph_transition_result__"
_MARKER = NameExpr(_MARKER_NAME)


@dataclass(frozen=True)
class _Pair:
    symbolic: Expr
    concrete: Expr


@dataclass(frozen=True)
class _Context:
    caller: str
    binding_name: str
    binding_index: int
    line: int
    block: object


@dataclass(frozen=True)
class _Evaluation:
    invocations: tuple[dict[str, object], ...]
    unresolved: bool = False


@dataclass(frozen=True)
class _ContextEvaluation:
    context: _Context
    invocations: tuple[dict[str, object], ...]
    unresolved: bool


def _text(value: object) -> str:
    return str(value or "").strip()


def _unwrap(expression: Expr) -> Expr:
    if isinstance(expression, TryExpr):
        return _unwrap(expression.expr)
    if (
        isinstance(expression, CallExpr)
        and isinstance(expression.callee, NameExpr)
        and expression.callee.name == "Ok"
        and len(expression.args) == 1
    ):
        return _unwrap(expression.args[0])
    return expression


def _substitute(expression: Expr, values: Mapping[str, Expr]) -> Expr:
    if isinstance(expression, NameExpr):
        return values.get(expression.name, expression)
    if isinstance(expression, FieldExpr):
        return FieldExpr(_substitute(expression.base, values), expression.field)
    if isinstance(expression, UnaryExpr):
        return UnaryExpr(expression.op, _substitute(expression.expr, values))
    if isinstance(expression, BinaryExpr):
        return BinaryExpr(
            expression.op,
            _substitute(expression.left, values),
            _substitute(expression.right, values),
        )
    if isinstance(expression, CallExpr):
        return CallExpr(
            _substitute(expression.callee, values),
            tuple(_substitute(argument, values) for argument in expression.args),
        )
    if isinstance(expression, TryExpr):
        return TryExpr(_substitute(expression.expr, values))
    return expression


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


def _ground_value(expression: Expr, constants: frozenset[str]) -> bool:
    if isinstance(expression, (BoolExpr, NumberExpr)):
        return True
    if isinstance(expression, NameExpr):
        return expression.name in constants
    if isinstance(expression, CallExpr) and isinstance(expression.callee, NameExpr):
        return expression.callee.name in constants and all(
            _ground_value(argument, constants) for argument in expression.args
        )
    return False


def _simplify(
    expression: Expr,
    *,
    products: Mapping[str, ProductDecl],
    constants: frozenset[str],
) -> Expr:
    if isinstance(expression, FieldExpr):
        base = _simplify(expression.base, products=products, constants=constants)
        if isinstance(base, CallExpr) and isinstance(base.callee, NameExpr):
            declaration = products.get(base.callee.name)
            if declaration is not None and len(base.args) == len(declaration.fields):
                index = next(
                    (
                        index
                        for index, field in enumerate(declaration.fields)
                        if field.name == expression.field
                    ),
                    None,
                )
                if index is not None:
                    return _simplify(
                        base.args[index], products=products, constants=constants
                    )
        return FieldExpr(base, expression.field)
    if isinstance(expression, TryExpr):
        return TryExpr(
            _simplify(expression.expr, products=products, constants=constants)
        )
    if isinstance(expression, UnaryExpr):
        value = _simplify(expression.expr, products=products, constants=constants)
        if expression.op == "!" and isinstance(value, BoolExpr):
            return BoolExpr(not value.value)
        return UnaryExpr(expression.op, value)
    if isinstance(expression, CallExpr):
        return CallExpr(
            expression.callee,
            tuple(
                _simplify(argument, products=products, constants=constants)
                for argument in expression.args
            ),
        )
    if isinstance(expression, BinaryExpr):
        left = _simplify(expression.left, products=products, constants=constants)
        right = _simplify(expression.right, products=products, constants=constants)
        if expression.op in {"==", "!="}:
            if _ground_value(left, constants) and _ground_value(right, constants):
                equal = left == right
                return BoolExpr(equal if expression.op == "==" else not equal)
        if expression.op == "&":
            if isinstance(left, BoolExpr):
                return right if left.value else BoolExpr(False)
            if isinstance(right, BoolExpr):
                return left if right.value else BoolExpr(False)
        if expression.op == "|":
            if isinstance(left, BoolExpr):
                return BoolExpr(True) if left.value else right
            if isinstance(right, BoolExpr):
                return BoolExpr(True) if right.value else left
        return BinaryExpr(expression.op, left, right)
    return expression


def _truth(
    expression: Expr,
    *,
    products: Mapping[str, ProductDecl],
    constants: frozenset[str],
) -> bool | None:
    simplified = _simplify(expression, products=products, constants=constants)
    return simplified.value if isinstance(simplified, BoolExpr) else None


class _Evaluator:
    def __init__(
        self,
        *,
        functions: Mapping[str, FunctionDecl],
        externs: Mapping[str, ExternDecl],
        aliases: Mapping[str, TypeRef],
        products: Mapping[str, ProductDecl],
        constants: frozenset[str],
        caller: str,
        line: int,
        path: Sequence[str],
    ) -> None:
        self.functions = functions
        self.externs = externs
        self.aliases = aliases
        self.products = products
        self.constants = constants
        self.caller = caller
        self.line = line
        self.path = tuple(path)

    def evaluate(
        self,
        pair: _Pair,
        *,
        visited: frozenset[str] = frozenset(),
        path: Sequence[str] | None = None,
    ) -> _Evaluation:
        symbolic = pair.symbolic
        concrete = pair.concrete
        current_path = tuple(path or self.path)

        if isinstance(symbolic, FieldExpr) and isinstance(concrete, FieldExpr):
            return self.evaluate(
                _Pair(symbolic.base, concrete.base),
                visited=visited,
                path=current_path,
            )
        if isinstance(symbolic, TryExpr) and isinstance(concrete, TryExpr):
            return self.evaluate(
                _Pair(symbolic.expr, concrete.expr),
                visited=visited,
                path=current_path,
            )
        if isinstance(symbolic, UnaryExpr) and isinstance(concrete, UnaryExpr):
            return self.evaluate(
                _Pair(symbolic.expr, concrete.expr),
                visited=visited,
                path=current_path,
            )
        if isinstance(symbolic, BinaryExpr) and isinstance(concrete, BinaryExpr):
            left = self.evaluate(
                _Pair(symbolic.left, concrete.left),
                visited=visited,
                path=current_path,
            )
            right = self.evaluate(
                _Pair(symbolic.right, concrete.right),
                visited=visited,
                path=current_path,
            )
            return _Evaluation(
                (*left.invocations, *right.invocations),
                left.unresolved or right.unresolved,
            )
        if not isinstance(symbolic, CallExpr) or not isinstance(concrete, CallExpr):
            return _Evaluation(())

        nested: list[dict[str, object]] = []
        unresolved = False
        for symbolic_argument, concrete_argument in zip(
            symbolic.args, concrete.args, strict=False
        ):
            result = self.evaluate(
                _Pair(symbolic_argument, concrete_argument),
                visited=visited,
                path=current_path,
            )
            nested.extend(result.invocations)
            unresolved = unresolved or result.unresolved

        if not isinstance(symbolic.callee, NameExpr) or not isinstance(
            concrete.callee, NameExpr
        ):
            return _Evaluation(tuple(nested), unresolved or _contains_marker(symbolic))
        name = symbolic.callee.name
        external = self.externs.get(name)
        if external is not None:
            if not _contains_marker(symbolic):
                return _Evaluation(tuple(nested), unresolved)
            rendered = render_expr(
                _simplify(
                    concrete,
                    products=self.products,
                    constants=self.constants,
                )
            )
            nested.append(
                {
                    "operation": name,
                    "expression": rendered,
                    "failure_type": _failure_type(external.return_type, self.aliases),
                    "sequence": 0,
                    "effectful": True,
                    "kind": "effect-invocation",
                    "provenance": CONSUMER_PROVENANCE,
                    "source": {"line": self.line, "column": 1},
                    "caller": self.caller,
                    "dataflow_path": [*current_path, name],
                }
            )
            return _Evaluation(tuple(nested), unresolved)

        function = self.functions.get(name)
        if function is None:
            return _Evaluation(tuple(nested), unresolved)
        if name in visited or len(function.params) != len(symbolic.args):
            return _Evaluation(
                tuple(nested), unresolved or _contains_marker(symbolic)
            )
        symbolic_values = {
            parameter.name: argument
            for parameter, argument in zip(function.params, symbolic.args, strict=True)
        }
        concrete_values = {
            parameter.name: argument
            for parameter, argument in zip(function.params, concrete.args, strict=True)
        }
        next_path = (*current_path, name)
        next_visited = visited | {name}
        if function.expression is not None:
            body = _Pair(
                _substitute(function.expression, symbolic_values),
                _substitute(function.expression, concrete_values),
            )
            result = self.evaluate(body, visited=next_visited, path=next_path)
            return _Evaluation(
                (*nested, *result.invocations),
                unresolved or result.unresolved,
            )
        if function.guards:
            for clause in function.guards:
                if clause.condition is None:
                    selected = _Pair(
                        _substitute(clause.value, symbolic_values),
                        _substitute(clause.value, concrete_values),
                    )
                    result = self.evaluate(
                        selected, visited=next_visited, path=next_path
                    )
                    return _Evaluation(
                        (*nested, *result.invocations),
                        unresolved or result.unresolved,
                    )
                condition = _substitute(clause.condition, concrete_values)
                condition_truth = _truth(
                    condition,
                    products=self.products,
                    constants=self.constants,
                )
                if condition_truth is False:
                    continue
                if condition_truth is None:
                    return _Evaluation(
                        tuple(nested), unresolved or _contains_marker(symbolic)
                    )
                selected = _Pair(
                    _substitute(clause.value, symbolic_values),
                    _substitute(clause.value, concrete_values),
                )
                result = self.evaluate(
                    selected, visited=next_visited, path=next_path
                )
                return _Evaluation(
                    (*nested, *result.invocations),
                    unresolved or result.unresolved,
                )
            return _Evaluation(tuple(nested), unresolved or _contains_marker(symbolic))
        return _Evaluation(tuple(nested), unresolved)


def _direct_call_name(expression: Expr) -> str | None:
    value = _unwrap(expression)
    if isinstance(value, CallExpr) and isinstance(value.callee, NameExpr):
        return value.callee.name
    return None


def _consumer_contexts(
    model: CompilationModel,
    next_function: str,
) -> tuple[_Context, ...]:
    contexts: list[_Context] = []
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
            _Context(
                caller=block.name,
                binding_name=binding.name,
                binding_index=index,
                line=binding.line,
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
    products: Mapping[str, ProductDecl],
    constants: frozenset[str],
) -> tuple[_Pair | None, bool]:
    clauses: list[tuple[str | None, str]] = []
    for original in source.splitlines():
        stripped = original.strip()
        if "=>" not in stripped:
            return None, True
        condition, value = stripped.split("=>", 1)
        clauses.append((None if condition.strip() == "_" else condition.strip(), value.strip()))
    for condition_source, value_source in clauses:
        if condition_source is None:
            try:
                value = parse_expr(value_source)
            except Exception:
                return None, True
            return _Pair(
                _substitute(value, symbolic_values),
                _substitute(value, concrete_values),
            ), False
        try:
            condition = _substitute(parse_expr(condition_source), concrete_values)
        except Exception:
            return None, True
        condition_truth = _truth(
            condition,
            products=products,
            constants=constants,
        )
        if condition_truth is False:
            continue
        if condition_truth is None:
            return None, True
        try:
            value = parse_expr(value_source)
        except Exception:
            return None, True
        return _Pair(
            _substitute(value, symbolic_values),
            _substitute(value, concrete_values),
        ), False
    return None, True


def _evaluate_context(
    context: _Context,
    *,
    branch_value: Expr,
    evaluator_factory: object,
    products: Mapping[str, ProductDecl],
    constants: frozenset[str],
    next_function: str,
) -> _ContextEvaluation:
    block = context.block
    symbolic_values: dict[str, Expr] = {context.binding_name: _MARKER}
    concrete_values: dict[str, Expr] = {context.binding_name: branch_value}
    invocations: list[dict[str, object]] = []
    unresolved = False

    for binding in block.bindings[context.binding_index + 1 :]:
        if binding.kind == "conditional":
            pair, failed = _conditional_pair(
                binding.source,
                symbolic_values=symbolic_values,
                concrete_values=concrete_values,
                products=products,
                constants=constants,
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
            pair = _Pair(
                _substitute(expression, symbolic_values),
                _substitute(expression, concrete_values),
            )
        evaluator = evaluator_factory(
            caller=context.caller,
            line=binding.line,
            path=(next_function, f"{context.caller}.{context.binding_name}"),
        )
        result = evaluator.evaluate(pair)
        invocations.extend(result.invocations)
        unresolved = unresolved or result.unresolved
        symbolic_values[binding.name] = pair.symbolic
        concrete_values[binding.name] = pair.concrete

    try:
        final_expression = parse_expr(block.final_source)
    except Exception:
        return _ContextEvaluation(context, tuple(invocations), True)
    final_pair = _Pair(
        _substitute(final_expression, symbolic_values),
        _substitute(final_expression, concrete_values),
    )
    evaluator = evaluator_factory(
        caller=context.caller,
        line=block.final_line,
        path=(next_function, f"{context.caller}.{context.binding_name}"),
    )
    final_result = evaluator.evaluate(final_pair)
    invocations.extend(final_result.invocations)
    unresolved = unresolved or final_result.unresolved
    return _ContextEvaluation(context, tuple(invocations), unresolved)


def _branch_for_transition(
    branches: Sequence[object],
    transition: Mapping[str, object],
) -> object | None:
    source = transition.get("source", {})
    line = int(source.get("line", 0)) if isinstance(source, Mapping) else 0
    source_state = _text(transition.get("source_state"))
    target_state = _text(transition.get("target_state"))
    synthesized = bool(transition.get("synthesized_failure"))
    candidates = [item for item in branches if int(getattr(item, "line", 0)) == line]
    if synthesized:
        return candidates[0] if candidates else None
    for item in candidates:
        target = getattr(item, "target", "")
        resolved = source_state if target == "__same__" else _text(target)
        if resolved == target_state:
            return item
    return candidates[0] if len(candidates) == 1 else None


def _conditional_block_values(
    model: CompilationModel,
    function_name: str | None,
) -> tuple[tuple[int, str, Expr], ...]:
    if function_name is None:
        return ()
    block = next((item for item in model.blocks if item.name == function_name), None)
    if block is None:
        return ()
    values: list[tuple[int, str, Expr]] = []
    for binding in block.bindings:
        if binding.kind != "conditional":
            continue
        for offset, original in enumerate(binding.source.splitlines(), start=1):
            stripped = original.strip()
            arrow = stripped.find("=>")
            if arrow < 0:
                continue
            condition_text = stripped[:arrow].strip()
            value_text = stripped[arrow + 2 :].strip()
            if not value_text:
                continue
            try:
                value = parse_expr(value_text)
                condition = (
                    "otherwise"
                    if condition_text == "_"
                    else render_expr(parse_expr(condition_text))
                )
            except Exception:
                continue
            values.append((binding.line + offset, condition, value))
    return tuple(values)


def _block_value_for_transition(
    values: Sequence[tuple[int, str, Expr]],
    transition: Mapping[str, object],
) -> Expr | None:
    source = transition.get("source", {})
    line = int(source.get("line", 0)) if isinstance(source, Mapping) else 0
    raw = _text(transition.get("condition_raw") or transition.get("condition"))
    condition = "otherwise" if raw in {"", "otherwise", "next"} else raw
    exact = [
        value
        for candidate_line, candidate_condition, value in values
        if candidate_line == line and candidate_condition == condition
    ]
    if exact:
        return exact[0]
    matching = [
        value
        for _, candidate_condition, value in values
        if candidate_condition == condition
    ]
    return matching[0] if len(matching) == 1 else None


def _action_value(invocations: Sequence[Mapping[str, object]]) -> dict[str, object] | None:
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
        "kind": "operation-invocation" if len(expressions) == 1 else "operation-sequence",
        "effectful": True,
        "provenance": ACTION_PROVENANCE,
        "source": dict(source) if isinstance(source, Mapping) else source,
    }


def _diagnostic(code: str, message: str, line: int) -> dict[str, object]:
    return {
        "severity": "warning",
        "code": code,
        "message": message,
        "line": line,
    }


def _sequence_key(invocations: Sequence[Mapping[str, object]]) -> tuple[tuple[str, str | None], ...]:
    return tuple(
        (_text(item.get("expression")), item.get("failure_type"))
        for item in invocations
    )


def attach_transition_result_consumer_actions(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Attribute post-transition operations through proven immutable result flow.

    The pass follows the machine next-function result into a caller binding and then
    through aliases and pure helpers until an external operation consumes that
    result. It never substitutes Target State or Emitted Output for an operation.
    """

    result = deepcopy(machine_view)
    machine = next(
        (item for item in model.machines if item.name == result.get("name")),
        None,
    )
    if machine is None or not isinstance(machine.next_expr, CallExpr) or not isinstance(
        machine.next_expr.callee, NameExpr
    ):
        return result
    next_function = machine.next_expr.callee.name
    contexts = _consumer_contexts(model, next_function)
    if not contexts:
        analysis = dict(result.get("analysis", {}))
        analysis["transition_result_consumer_action_version"] = 1
        analysis["transition_result_consumer_context_count"] = 0
        result["analysis"] = analysis
        return result

    products = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, ProductDecl)
    }
    sums = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, SumDecl)
    }
    constants = frozenset(
        variant.name for declaration in sums.values() for variant in declaration.variants
    )
    functions = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, FunctionDecl)
    }
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

    state_decl = products.get(machine.state_param.ty.name)
    if state_decl is None or not isinstance(machine.selector, FieldExpr):
        return result
    selector_index = next(
        (
            index
            for index, field in enumerate(state_decl.fields)
            if field.name == machine.selector.field
        ),
        None,
    )
    if selector_index is None:
        return result
    selector_sum = sums.get(state_decl.fields[selector_index].ty.name)
    if selector_sum is None:
        return result
    branches = _root_branches(
        next_function,
        functions=functions,
        state_decl=state_decl,
        selector_index=selector_index,
        variants={item.name for item in selector_sum.variants},
        root_state_param=machine.state_param.name,
    )
    block_values = _conditional_block_values(model, next_function)

    def evaluator_factory(*, caller: str, line: int, path: Sequence[str]) -> _Evaluator:
        return _Evaluator(
            functions=functions,
            externs=externs,
            aliases=aliases,
            products=products,
            constants=constants,
            caller=caller,
            line=line,
            path=path,
        )

    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
    transitions: list[dict[str, object]] = []
    consumer_action_count = 0
    ambiguous_count = 0
    unresolved_count = 0

    for original in result.get("transitions", []):
        transition = dict(original)
        branch = _branch_for_transition(branches, transition)
        branch_value = getattr(branch, "value", None) if branch is not None else None
        if branch_value is None:
            branch_value = _block_value_for_transition(block_values, transition)
        if branch_value is None:
            transitions.append(transition)
            continue

        evaluations = [
            _evaluate_context(
                context,
                branch_value=branch_value,
                evaluator_factory=evaluator_factory,
                products=products,
                constants=constants,
                next_function=next_function,
            )
            for context in contexts
        ]
        source = transition.get("source", {})
        line = int(source.get("line", 1)) if isinstance(source, Mapping) else 1
        if any(item.unresolved for item in evaluations):
            unresolved_count += 1
            diagnostics.append(
                _diagnostic(
                    _UNRESOLVED_CODE,
                    (
                        f"transition result from `{next_function}` reaches a caller path "
                        "whose operation cannot be proven; Action remains unchanged"
                    ),
                    line,
                )
            )
            transitions.append(transition)
            continue

        by_key: dict[tuple[tuple[str, str | None], ...], _ContextEvaluation] = {}
        for evaluation in evaluations:
            by_key.setdefault(_sequence_key(evaluation.invocations), evaluation)
        if len(by_key) > 1:
            ambiguous_count += 1
            diagnostics.append(
                _diagnostic(
                    _AMBIGUOUS_CODE,
                    (
                        f"transition result from `{next_function}` has multiple caller "
                        "operation sequences; no downstream Action is invented"
                    ),
                    line,
                )
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
            (_text(item.get("expression")), item.get("failure_type")) for item in effects
        }
        for invocation in downstream:
            key = (_text(invocation.get("expression")), invocation.get("failure_type"))
            if key not in effect_keys:
                effects.append(dict(invocation))
                effect_keys.add(key)
        for sequence, invocation in enumerate(effects, start=1):
            invocation["sequence"] = sequence
        transition["effect_invocations"] = effects
        transition["action"] = _action_value(combined)
        transition["action_result_dataflow"] = {
            "provenance": CONSUMER_PROVENANCE,
            "caller": selected.context.caller,
            "binding": selected.context.binding_name,
            "path": [
                next_function,
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

    analysis = dict(result.get("analysis", {}))
    analysis.update(
        {
            "transition_result_consumer_action_version": 1,
            "transition_result_consumer_context_count": len(contexts),
            "transition_result_consumer_action_count": consumer_action_count,
            "transition_result_consumer_ambiguous_count": ambiguous_count,
            "transition_result_consumer_unresolved_count": unresolved_count,
        }
    )
    result["transitions"] = transitions
    result["diagnostics"] = diagnostics
    result["analysis"] = analysis
    return result


__all__ = [
    "ACTION_PROVENANCE",
    "CONSUMER_PROVENANCE",
    "attach_transition_result_consumer_actions",
]

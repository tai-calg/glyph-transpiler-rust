from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from .artifacts import CompilationModel
from .compiler import (
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    FieldExpr,
    FunctionDecl,
    NameExpr,
    TryExpr,
    UnaryExpr,
    parse_expr,
)
from .execution_ir import render_expr
from .machine import MachineDecl


INPUT_PREIMAGE_VERSION = 1
_INPUT_PROVENANCE = "decision-output-preimage"
_EXPANDED_CONFIDENCE = "dataflow-expanded"
_UNRESOLVED_CODE = "STIR_INPUT_PREIMAGE_UNRESOLVED"


@dataclass(frozen=True)
class _Candidate:
    atom: BinaryExpr
    local_name: str
    pattern: Expr
    variant: str
    definition: Expr


@dataclass(frozen=True)
class _Discriminator:
    atom: BinaryExpr
    local_name: str
    pattern: Expr
    variant: str
    definition: CallExpr
    decision: FunctionDecl


@dataclass(frozen=True)
class _Preimage:
    display: str
    expression: str
    exact: Expr | None
    fallback: bool
    roots: tuple[str, ...]
    path: tuple[str, ...]
    payload_bindings: Mapping[str, Expr]


def _warning(message: str, line: int) -> dict[str, object]:
    return {
        "severity": "warning",
        "code": _UNRESOLVED_CODE,
        "message": message,
        "line": line,
    }


def _next_name(machine: MachineDecl) -> str | None:
    expression = machine.next_expr
    if not isinstance(expression, CallExpr) or not isinstance(expression.callee, NameExpr):
        return None
    return expression.callee.name


def _block_definitions(model: CompilationModel, function_name: str | None) -> dict[str, Expr]:
    if function_name is None:
        return {}
    block = next((item for item in model.blocks if item.name == function_name), None)
    if block is None:
        return {}
    definitions: dict[str, Expr] = {}
    for binding in block.bindings:
        if binding.kind != "expression":
            continue
        try:
            definitions[binding.name] = parse_expr(binding.source)
        except Exception:
            continue
    return definitions


def _flatten_and(expression: Expr) -> list[Expr]:
    if isinstance(expression, BinaryExpr) and expression.op == "&":
        return [*_flatten_and(expression.left), *_flatten_and(expression.right)]
    return [expression]


def _combine(expressions: Sequence[Expr], operator: str) -> Expr | None:
    iterator = iter(expressions)
    try:
        result = next(iterator)
    except StopIteration:
        return None
    for expression in iterator:
        result = BinaryExpr(operator, result, expression)
    return result


def _variant(expression: Expr) -> tuple[str | None, tuple[Expr, ...]]:
    if isinstance(expression, NameExpr):
        return expression.name, ()
    if isinstance(expression, CallExpr) and isinstance(expression.callee, NameExpr):
        return expression.callee.name, expression.args
    return None, ()


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


def _expand_definitions(
    expression: Expr,
    definitions: Mapping[str, Expr],
    visited: frozenset[str] = frozenset(),
) -> Expr:
    if isinstance(expression, NameExpr):
        if expression.name in definitions and expression.name not in visited:
            return _expand_definitions(
                definitions[expression.name],
                definitions,
                visited | {expression.name},
            )
        return expression
    if isinstance(expression, FieldExpr):
        return FieldExpr(_expand_definitions(expression.base, definitions, visited), expression.field)
    if isinstance(expression, UnaryExpr):
        return UnaryExpr(expression.op, _expand_definitions(expression.expr, definitions, visited))
    if isinstance(expression, BinaryExpr):
        return BinaryExpr(
            expression.op,
            _expand_definitions(expression.left, definitions, visited),
            _expand_definitions(expression.right, definitions, visited),
        )
    if isinstance(expression, CallExpr):
        return CallExpr(
            expression.callee,
            tuple(
                _expand_definitions(argument, definitions, visited)
                for argument in expression.args
            ),
        )
    if isinstance(expression, TryExpr):
        return TryExpr(_expand_definitions(expression.expr, definitions, visited))
    return expression


def _contains_name(expression: Expr, name: str) -> bool:
    if isinstance(expression, NameExpr):
        return expression.name == name
    if isinstance(expression, FieldExpr):
        return _contains_name(expression.base, name)
    if isinstance(expression, UnaryExpr):
        return _contains_name(expression.expr, name)
    if isinstance(expression, BinaryExpr):
        return _contains_name(expression.left, name) or _contains_name(expression.right, name)
    if isinstance(expression, CallExpr):
        return any(_contains_name(argument, name) for argument in expression.args)
    if isinstance(expression, TryExpr):
        return _contains_name(expression.expr, name)
    return False


def _input_roots(expression: Expr, input_names: frozenset[str]) -> tuple[str, ...]:
    roots: set[str] = set()

    def visit(item: Expr) -> None:
        if isinstance(item, NameExpr):
            if item.name in input_names:
                roots.add(f"input:{item.name}")
            return
        if isinstance(item, FieldExpr):
            visit(item.base)
            return
        if isinstance(item, UnaryExpr):
            visit(item.expr)
            return
        if isinstance(item, BinaryExpr):
            visit(item.left)
            visit(item.right)
            return
        if isinstance(item, CallExpr):
            visit(item.callee)
            for argument in item.args:
                visit(argument)
            return
        if isinstance(item, TryExpr):
            visit(item.expr)

    visit(expression)
    return tuple(sorted(roots))


def _intermediate_discriminators(
    condition: Expr,
    *,
    definitions: Mapping[str, Expr],
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for atom in _flatten_and(condition):
        if not isinstance(atom, BinaryExpr) or atom.op != "==":
            continue
        for subject, pattern in ((atom.left, atom.right), (atom.right, atom.left)):
            if not isinstance(subject, NameExpr) or subject.name not in definitions:
                continue
            variant, _ = _variant(pattern)
            if variant is None:
                continue
            candidates.append(
                _Candidate(
                    atom=atom,
                    local_name=subject.name,
                    pattern=pattern,
                    variant=variant,
                    definition=_expand_definitions(
                        definitions[subject.name],
                        definitions,
                        frozenset({subject.name}),
                    ),
                )
            )
            break
    return candidates


def _expand_lambda_calls(
    expression: Expr,
    lambdas: Mapping[str, object],
    visited: frozenset[str] = frozenset(),
) -> Expr:
    if isinstance(expression, FieldExpr):
        return FieldExpr(_expand_lambda_calls(expression.base, lambdas, visited), expression.field)
    if isinstance(expression, UnaryExpr):
        return UnaryExpr(expression.op, _expand_lambda_calls(expression.expr, lambdas, visited))
    if isinstance(expression, BinaryExpr):
        return BinaryExpr(
            expression.op,
            _expand_lambda_calls(expression.left, lambdas, visited),
            _expand_lambda_calls(expression.right, lambdas, visited),
        )
    if isinstance(expression, CallExpr):
        arguments = tuple(
            _expand_lambda_calls(argument, lambdas, visited)
            for argument in expression.args
        )
        if isinstance(expression.callee, NameExpr):
            lowering = lambdas.get(expression.callee.name)
            if lowering is not None and expression.callee.name not in visited and len(arguments) == 1:
                try:
                    body = parse_expr(str(lowering.body))
                except Exception:
                    return CallExpr(expression.callee, arguments)
                restored = _substitute(body, {str(lowering.parameter): arguments[0]})
                return _expand_lambda_calls(
                    restored,
                    lambdas,
                    visited | {expression.callee.name},
                )
        return CallExpr(expression.callee, arguments)
    if isinstance(expression, TryExpr):
        return TryExpr(_expand_lambda_calls(expression.expr, lambdas, visited))
    return expression


def _resolve_block_discriminator(
    candidate: _Candidate,
    definition: CallExpr,
    public: FunctionDecl,
    *,
    functions: Mapping[str, FunctionDecl],
    blocks: Mapping[str, object],
    lambdas: Mapping[str, object],
) -> _Discriminator | None:
    block = blocks.get(public.name)
    if block is None:
        return None
    try:
        final = parse_expr(str(block.final_source))
    except Exception:
        return None
    if not isinstance(final, NameExpr):
        return None
    bindings = list(block.bindings)
    final_indices = [index for index, binding in enumerate(bindings) if binding.name == final.name]
    if len(final_indices) != 1 or final_indices[0] != len(bindings) - 1:
        return None
    if len(public.params) != len(definition.args):
        return None

    available: dict[str, Expr] = {
        parameter.name: argument
        for parameter, argument in zip(public.params, definition.args)
    }
    for binding in bindings:
        helper = functions.get(binding.value_helper)
        if helper is None:
            return None
        try:
            helper_arguments = tuple(available[parameter.name] for parameter in helper.params)
        except KeyError:
            return None
        substitutions = {
            parameter.name: argument
            for parameter, argument in zip(helper.params, helper_arguments)
        }
        if binding.name == final.name:
            if binding.kind != "conditional" or not helper.guards:
                return None
            decision = replace(helper, name=public.name)
            return _Discriminator(
                atom=candidate.atom,
                local_name=candidate.local_name,
                pattern=candidate.pattern,
                variant=candidate.variant,
                definition=CallExpr(NameExpr(public.name), helper_arguments),
                decision=decision,
            )
        if binding.kind != "expression" or helper.expression is None or helper.guards:
            return None
        restored = _substitute(helper.expression, substitutions)
        available[binding.name] = _expand_lambda_calls(restored, lambdas)
    return None


def _resolve_discriminator(
    candidate: _Candidate,
    *,
    functions: Mapping[str, FunctionDecl],
    blocks: Mapping[str, object],
    lambdas: Mapping[str, object],
) -> _Discriminator | None:
    definition = candidate.definition
    if not (
        isinstance(definition, CallExpr)
        and isinstance(definition.callee, NameExpr)
    ):
        return None
    public = functions.get(definition.callee.name)
    if public is None:
        return None
    if public.guards:
        return _Discriminator(
            atom=candidate.atom,
            local_name=candidate.local_name,
            pattern=candidate.pattern,
            variant=candidate.variant,
            definition=definition,
            decision=public,
        )
    return _resolve_block_discriminator(
        candidate,
        definition,
        public,
        functions=functions,
        blocks=blocks,
        lambdas=lambdas,
    )


def _payload_mapping(pattern: Expr, value: Expr) -> dict[str, Expr] | None:
    pattern_variant, pattern_args = _variant(pattern)
    value_variant, value_args = _variant(value)
    if pattern_variant is None or pattern_variant != value_variant:
        return None
    if len(pattern_args) != len(value_args):
        return None
    mapping: dict[str, Expr] = {}
    for binder, payload in zip(pattern_args, value_args):
        if not isinstance(binder, NameExpr) or binder.name == "_":
            continue
        mapping[binder.name] = payload
    return mapping


def _same_payload_bindings(candidates: Sequence[Mapping[str, Expr]]) -> dict[str, Expr]:
    if not candidates:
        return {}
    names = set(candidates[0])
    if any(set(candidate) != names for candidate in candidates[1:]):
        return {}
    result: dict[str, Expr] = {}
    for name in names:
        rendered = {render_expr(candidate[name]) for candidate in candidates}
        if len(rendered) != 1:
            return {}
        result[name] = candidates[0][name]
    return result


def _resolve_preimage(
    discriminator: _Discriminator,
    *,
    input_names: frozenset[str],
    forbidden_names: frozenset[str] = frozenset(),
) -> _Preimage | None:
    decision = discriminator.decision
    if len(decision.params) != len(discriminator.definition.args):
        return None
    substitutions = {
        parameter.name: argument
        for parameter, argument in zip(decision.params, discriminator.definition.args)
    }

    prior_different: list[Expr] = []
    exact_matches: list[Expr] = []
    fallback_match = False
    payload_candidates: list[Mapping[str, Expr]] = []

    for clause in decision.guards:
        value = _substitute(clause.value, substitutions)
        result_variant, _ = _variant(value)
        condition = (
            None
            if clause.condition is None
            else _substitute(clause.condition, substitutions)
        )
        matches = result_variant == discriminator.variant

        if matches:
            payload = _payload_mapping(discriminator.pattern, value)
            if payload is None:
                return None
            payload_candidates.append(payload)
            if condition is None:
                fallback_match = True
                prior = _combine(prior_different, "|")
                exact_matches.append(
                    BoolExpr(True) if prior is None else UnaryExpr("!", prior)
                )
            else:
                prior = _combine(prior_different, "|")
                exact_matches.append(
                    condition
                    if prior is None
                    else BinaryExpr("&", condition, UnaryExpr("!", prior))
                )
        elif condition is not None:
            prior_different.append(condition)

    if not exact_matches:
        return None

    exact = _combine(exact_matches, "|")
    assert exact is not None
    if any(_contains_name(exact, name) for name in forbidden_names):
        return None
    roots = _input_roots(exact, input_names)
    if not roots and not fallback_match:
        return None

    only_fallback = fallback_match and len(exact_matches) == 1
    display = "otherwise" if only_fallback else render_expr(exact)
    return _Preimage(
        display=display,
        expression=render_expr(exact),
        exact=exact,
        fallback=only_fallback,
        roots=roots or tuple(f"input:{name}" for name in sorted(input_names)),
        path=(
            *sorted(input_names),
            f"{discriminator.decision.name}(...)",
            discriminator.local_name,
            discriminator.variant,
        ),
        payload_bindings=_same_payload_bindings(payload_candidates),
    )


def _action_display(action: object) -> str:
    if isinstance(action, Mapping):
        return str(action.get("display") or action.get("expression") or "")
    return "" if action is None else str(action)


def _display_label(transition: Mapping[str, object]) -> str:
    trigger = transition.get("trigger")
    label = ""
    if isinstance(trigger, Mapping):
        prefix = "? " if trigger.get("role") == "provisional-trigger" else ""
        label = prefix + str(trigger.get("display") or "")
    guards = [str(item) for item in transition.get("guards", []) if str(item)]
    if guards:
        guard = "&".join(guards)
        label += f" [{guard}]" if label else f"[{guard}]"
    unknown = [
        str(item)
        for item in transition.get("unclassified_conditions", [])
        if str(item)
    ]
    if unknown:
        value = "&".join(unknown)
        label += f" ? {value}" if label else f"? {value}"
    action = _action_display(transition.get("action"))
    if action:
        label += f" / {action}" if label else f"/ {action}"
    failure = str(transition.get("failure_type") or "")
    if failure:
        label += f" | {failure}"
    return label


def _mark_unresolved(
    transition: dict[str, object],
    *,
    message: str,
    line: int,
    generated: list[dict[str, object]],
) -> None:
    trigger = transition.get("trigger")
    if isinstance(trigger, Mapping):
        value = dict(trigger)
        display = str(value.get("display") or value.get("expression") or "")
        value["role"] = "provisional-trigger"
        value["confidence"] = "fallback"
        value["provenance"] = "intermediate-decision-unresolved"
        transition["trigger"] = value
        transition["event"] = (
            None
            if not display
            else display if display.startswith("? ") else f"? {display}"
        )
    classification = dict(transition.get("classification", {}))
    classification["confidence"] = "fallback"
    transition["classification"] = classification
    transition["display_label"] = _display_label(transition)
    generated.append(_warning(message, line))


def _refine_action(
    transition: dict[str, object],
    discriminator: _Discriminator,
    preimage: _Preimage,
) -> None:
    action = transition.get("action")
    if not isinstance(action, Mapping) or not preimage.payload_bindings:
        return
    if str(action.get("variant") or "") != discriminator.variant:
        return
    refined = _substitute(discriminator.pattern, preimage.payload_bindings)
    refined_variant, refined_payload = _variant(refined)
    if refined_variant != discriminator.variant:
        return
    value = dict(action)
    rendered = render_expr(refined)
    value["display"] = rendered
    value["expression"] = rendered
    value["payload"] = [render_expr(item) for item in refined_payload]
    value["value_provenance"] = _INPUT_PROVENANCE
    transition["action"] = value


def expand_machine_transition_inputs(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Expand local decision discriminators into machine-input preimages.

    The pass is deliberately conservative. It rewrites a trigger only when a local
    immutable binding is a direct call to a guarded pure function and the compared
    output variant can be mapped back to input-rooted guard predicates.
    """

    result = deepcopy(machine_view)
    machine = next(
        (item for item in model.machines if item.name == result.get("name")),
        None,
    )
    if machine is None:
        return result

    functions = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, FunctionDecl)
    }
    blocks = {item.name: item for item in model.blocks}
    lambdas = {item.name: item for item in model.lambdas}
    definitions = _block_definitions(model, _next_name(machine))
    input_names = frozenset(parameter.name for parameter in machine.input_params)
    if not definitions or not input_names:
        analysis = dict(result.get("analysis", {}))
        analysis["input_preimage_version"] = INPUT_PREIMAGE_VERSION
        analysis["expanded_input_preimage_count"] = 0
        analysis["unresolved_input_preimage_count"] = 0
        result["analysis"] = analysis
        return result

    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
    generated: list[dict[str, object]] = []
    transitions: list[dict[str, object]] = []
    expanded = 0
    unresolved = 0

    for original in result.get("transitions", []):
        transition = dict(original)
        raw = str(transition.get("condition_raw") or transition.get("condition") or "")
        if raw in {"", "otherwise", "next"}:
            transitions.append(transition)
            continue
        try:
            condition = parse_expr(raw)
        except Exception:
            transitions.append(transition)
            continue

        candidates = _intermediate_discriminators(
            condition,
            definitions=definitions,
        )
        if not candidates:
            transitions.append(transition)
            continue

        line = int(transition.get("source", {}).get("line", 1))
        if len(candidates) != 1:
            unresolved += 1
            _mark_unresolved(
                transition,
                message=(
                    "The transition contains multiple intermediate decision discriminators. "
                    "Partial Input-preimage expansion would drop conditions, so the original "
                    "trigger is preserved provisionally."
                ),
                line=line,
                generated=generated,
            )
            transitions.append(transition)
            continue

        candidate = candidates[0]
        trigger = transition.get("trigger")
        trigger_expression = (
            str(trigger.get("expression") or "")
            if isinstance(trigger, Mapping)
            else ""
        )
        if trigger_expression != render_expr(candidate.atom):
            unresolved += 1
            _mark_unresolved(
                transition,
                message=(
                    f"`{render_expr(candidate.atom)}` is only one part of the transition Input. "
                    "Expanding it alone would discard another event or input predicate, so the "
                    "combined trigger is preserved provisionally."
                ),
                line=line,
                generated=generated,
            )
            transitions.append(transition)
            continue

        discriminator = _resolve_discriminator(
            candidate,
            functions=functions,
            blocks=blocks,
            lambdas=lambdas,
        )
        if discriminator is None:
            unresolved += 1
            _mark_unresolved(
                transition,
                message=(
                    f"`{render_expr(candidate.atom)}` uses an intermediate decision value, "
                    "but its definition is not a direct guarded pure decision function. "
                    "The trigger is preserved provisionally instead of being claimed exact."
                ),
                line=line,
                generated=generated,
            )
            transitions.append(transition)
            continue

        preimage = _resolve_preimage(
            discriminator,
            input_names=input_names,
            forbidden_names=frozenset({machine.state_param.name}),
        )
        if preimage is None:
            unresolved += 1
            _mark_unresolved(
                transition,
                message=(
                    f"`{render_expr(discriminator.atom)}` is an intermediate decision "
                    "discriminator, but an input-only machine preimage could not be proven. "
                    "State-dependent or otherwise unresolved conditions are preserved "
                    "provisionally."
                ),
                line=line,
                generated=generated,
            )
            transitions.append(transition)
            continue

        expanded += 1
        transition["trigger"] = {
            "display": preimage.display,
            "expression": preimage.expression,
            "role": "inferred-trigger",
            "confidence": _EXPANDED_CONFIDENCE,
            "value_type": discriminator.decision.return_type.name,
            "variant": discriminator.variant,
            "provenance": _INPUT_PROVENANCE,
            "decision_function": discriminator.decision.name,
            "decision_variant": discriminator.variant,
            "provenance_roots": list(preimage.roots),
            "dataflow_path": list(preimage.path),
        }
        transition["event"] = preimage.display
        transition["input_preimage"] = {
            "version": INPUT_PREIMAGE_VERSION,
            "exact_expression": preimage.expression,
            "fallback_display": preimage.fallback,
            "decision_function": discriminator.decision.name,
            "decision_variant": discriminator.variant,
        }
        _refine_action(transition, discriminator, preimage)
        transition["display_label"] = _display_label(transition)
        classification = dict(transition.get("classification", {}))
        classification["confidence"] = _EXPANDED_CONFIDENCE
        transition["classification"] = classification
        transitions.append(transition)

    seen = {
        (item.get("code"), item.get("line"), item.get("message"))
        for item in diagnostics
    }
    for item in generated:
        key = (item.get("code"), item.get("line"), item.get("message"))
        if key not in seen:
            diagnostics.append(item)
            seen.add(key)

    analysis = dict(result.get("analysis", {}))
    analysis["input_preimage_version"] = INPUT_PREIMAGE_VERSION
    analysis["expanded_input_preimage_count"] = expanded
    analysis["unresolved_input_preimage_count"] = unresolved
    result["transitions"] = transitions
    result["diagnostics"] = diagnostics
    result["analysis"] = analysis
    return result

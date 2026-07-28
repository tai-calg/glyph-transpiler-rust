from __future__ import annotations

from pathlib import Path


PATH = Path("glyph/transition_input_provenance.py")
text = PATH.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"expected block not found:\n{old[:240]}")
    text = text.replace(old, new, 1)


replace_once(
    '''@dataclass(frozen=True)
class _Discriminator:
    atom: BinaryExpr
    local_name: str
    pattern: Expr
    variant: str
    definition: CallExpr
    decision: FunctionDecl
''',
    '''@dataclass(frozen=True)
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
''',
)

replace_once(
    '''def _input_roots(expression: Expr, input_names: frozenset[str]) -> tuple[str, ...]:
''',
    '''def _expand_definitions(
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
''',
)

old_find = '''def _find_discriminator(
    condition: Expr,
    *,
    definitions: Mapping[str, Expr],
    functions: Mapping[str, FunctionDecl],
) -> _Discriminator | None:
    for atom in _flatten_and(condition):
        if not isinstance(atom, BinaryExpr) or atom.op != "==":
            continue
        for subject, pattern in ((atom.left, atom.right), (atom.right, atom.left)):
            if not isinstance(subject, NameExpr):
                continue
            definition = definitions.get(subject.name)
            if not (
                isinstance(definition, CallExpr)
                and isinstance(definition.callee, NameExpr)
            ):
                continue
            decision = functions.get(definition.callee.name)
            if decision is None or not decision.guards:
                continue
            variant, _ = _variant(pattern)
            if variant is None:
                continue
            return _Discriminator(
                atom=atom,
                local_name=subject.name,
                pattern=pattern,
                variant=variant,
                definition=definition,
                decision=decision,
            )
    return None
'''
new_find = '''def _intermediate_discriminators(
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


def _resolve_discriminator(
    candidate: _Candidate,
    *,
    functions: Mapping[str, FunctionDecl],
) -> _Discriminator | None:
    definition = candidate.definition
    if not (
        isinstance(definition, CallExpr)
        and isinstance(definition.callee, NameExpr)
    ):
        return None
    decision = functions.get(definition.callee.name)
    if decision is None or not decision.guards:
        return None
    return _Discriminator(
        atom=candidate.atom,
        local_name=candidate.local_name,
        pattern=candidate.pattern,
        variant=candidate.variant,
        definition=definition,
        decision=decision,
    )
'''
replace_once(old_find, new_find)

replace_once(
    '''def _resolve_preimage(
    discriminator: _Discriminator,
    *,
    input_names: frozenset[str],
) -> _Preimage | None:
''',
    '''def _resolve_preimage(
    discriminator: _Discriminator,
    *,
    input_names: frozenset[str],
    forbidden_names: frozenset[str] = frozenset(),
) -> _Preimage | None:
''',
)

replace_once(
    '''    exact = _combine(exact_matches, "|")
    assert exact is not None
    roots = _input_roots(exact, input_names)
    if not roots and not fallback_match:
        return None
''',
    '''    exact = _combine(exact_matches, "|")
    assert exact is not None
    if any(_contains_name(exact, name) for name in forbidden_names):
        return None
    roots = _input_roots(exact, input_names)
    if not roots and not fallback_match:
        return None
''',
)

replace_once(
    '''def _refine_action(
''',
    '''def _mark_unresolved(
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
''',
)

old_loop = '''        discriminator = _find_discriminator(
            condition,
            definitions=definitions,
            functions=functions,
        )
        if discriminator is None:
            transitions.append(transition)
            continue

        preimage = _resolve_preimage(discriminator, input_names=input_names)
        line = int(transition.get("source", {}).get("line", 1))
        if preimage is None:
            unresolved += 1
            generated.append(
                _warning(
                    (
                        f"`{render_expr(discriminator.atom)}` is an intermediate decision "
                        "discriminator, but its machine-input preimage could not be proven. "
                        "The existing provisional trigger is preserved."
                    ),
                    line,
                )
            )
            transitions.append(transition)
            continue
'''
new_loop = '''        candidates = _intermediate_discriminators(
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

        discriminator = _resolve_discriminator(candidate, functions=functions)
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
'''
replace_once(old_loop, new_loop)

PATH.write_text(text, encoding="utf-8")

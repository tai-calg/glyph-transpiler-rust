from __future__ import annotations

from copy import deepcopy
from typing import Mapping, Sequence

from .artifacts import CompilationModel
from .compiler import (
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    FieldExpr,
    NameExpr,
    UnaryExpr,
    parse_expr,
)
from .execution_ir import render_expr
from .transition_condition_roles import _context, _facts
from .transition_input_provenance import (
    _block_definitions,
    _combine,
    _intermediate_discriminators,
    _next_name,
    _resolve_discriminator,
    _substitute,
    _variant,
)


ENABLING_CASE_VERSION = 1
MAX_ENABLING_CASES = 16
MAX_CONDITION_ATOMS = 64

_DECOMPOSITION_UNRESOLVED = "STIR_ENABLING_CASE_DECOMPOSITION_UNRESOLVED"
_PROVISIONAL_INPUT = "STIR_ENABLING_CASE_PROVISIONAL_INPUT"
_LEGACY_LOSSY = "STIR_ENABLING_CASE_LEGACY_PROJECTION_LOSSY"


def _warning(code: str, message: str, line: int) -> dict[str, object]:
    return {
        "severity": "warning",
        "code": code,
        "message": message,
        "line": max(1, line),
    }


def _flatten_and(expression: Expr) -> list[Expr]:
    if isinstance(expression, BinaryExpr) and expression.op == "&":
        return [*_flatten_and(expression.left), *_flatten_and(expression.right)]
    return [expression]


def _to_dnf(expression: Expr) -> list[list[Expr]] | None:
    """Return bounded DNF conjunctions without changing atom semantics."""

    atom_count = 0

    def visit(item: Expr) -> list[list[Expr]] | None:
        nonlocal atom_count
        if isinstance(item, BinaryExpr) and item.op == "|":
            left = visit(item.left)
            right = visit(item.right)
            if left is None or right is None:
                return None
            result = [*left, *right]
            return result if len(result) <= MAX_ENABLING_CASES else None
        if isinstance(item, BinaryExpr) and item.op == "&":
            left = visit(item.left)
            right = visit(item.right)
            if left is None or right is None:
                return None
            result: list[list[Expr]] = []
            for left_case in left:
                for right_case in right:
                    result.append([*left_case, *right_case])
                    if len(result) > MAX_ENABLING_CASES:
                        return None
            return result
        atom_count += 1
        if atom_count > MAX_CONDITION_ATOMS:
            return None
        return [[item]]

    return visit(expression)


def _root_input_name(expression: Expr, input_names: frozenset[str]) -> str | None:
    current = expression
    while isinstance(current, FieldExpr):
        current = current.base
    if isinstance(current, NameExpr) and current.name in input_names:
        return current.name
    return None


def _is_direct_input_subject(expression: Expr, context: object) -> bool:
    input_names = context.input_names
    if _root_input_name(expression, input_names) is not None:
        return True
    if (
        isinstance(expression, CallExpr)
        and isinstance(expression.callee, NameExpr)
        and expression.callee.name in context.externs
        and not expression.args
    ):
        return True
    return False


def _is_direct_input_atom(expression: Expr, context: object) -> bool:
    if _is_direct_input_subject(expression, context):
        return True
    if isinstance(expression, UnaryExpr) and expression.op == "!":
        return _is_direct_input_subject(expression.expr, context)
    if isinstance(expression, BinaryExpr) and expression.op in {
        "==",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
    }:
        for subject, value in (
            (expression.left, expression.right),
            (expression.right, expression.left),
        ):
            if not _is_direct_input_subject(subject, context):
                continue
            value_facts = _facts(value, context)
            if not value_facts.input_derived and not value_facts.state_derived and not value_facts.unknown:
                return True
    return False


def _guard_origin(expression: Expr, context: object) -> str:
    facts = _facts(expression, context)
    rendered = render_expr(expression)
    if facts.state_derived:
        return "state-condition"
    if rendered.startswith("@A") or rendered.startswith("@E") or "◇" in rendered or "□" in rendered:
        return "temporal-condition"
    if isinstance(expression, CallExpr):
        return "authored-derived-predicate"
    return "authored-derived-predicate"


def _input_pattern(
    expression: Expr,
    *,
    context: object,
    line: int,
    provisional: bool,
) -> dict[str, object]:
    facts = _facts(expression, context)
    return {
        "display": render_expr(expression),
        "expression": render_expr(expression),
        "kind": "provisional-input-pattern" if provisional else "direct-input-pattern",
        "origin": (
            "provisional-input-pattern"
            if provisional
            else "authored-direct-input-pattern"
        ),
        "confidence": "provisional" if provisional else "exact",
        "provenance_roots": sorted(facts.roots),
        "source_line": line,
    }


def _guard_term(
    expression: Expr,
    *,
    context: object,
    line: int,
    origin: str | None = None,
    display: str | None = None,
    excluded_clause_lines: Sequence[int] = (),
) -> dict[str, object]:
    facts = _facts(expression, context)
    result: dict[str, object] = {
        "display": render_expr(expression) if display is None else display,
        "expression": render_expr(expression),
        "kind": "fallback" if origin == "fallback" else "predicate",
        "origin": origin or _guard_origin(expression, context),
        "confidence": "exact",
        "provenance_roots": sorted(facts.roots),
        "source_line": line,
    }
    if excluded_clause_lines:
        result["excluded_clause_lines"] = list(excluded_clause_lines)
    return result


def _aggregate_guard(
    terms: Sequence[Mapping[str, object]],
    *,
    exact_expression: Expr | None = None,
) -> dict[str, object] | None:
    if not terms:
        return None
    displays = [str(item.get("display") or "") for item in terms if str(item.get("display") or "")]
    expressions = [
        str(item.get("expression") or "")
        for item in terms
        if str(item.get("expression") or "")
    ]
    return {
        "display": "&".join(displays),
        "expression": (
            render_expr(exact_expression)
            if exact_expression is not None
            else "&".join(expressions)
        ),
    }


def _classify_authored_conjunction(
    atoms: Sequence[Expr],
    *,
    context: object,
    line: int,
) -> tuple[dict[str, object] | None, list[dict[str, object]], list[str], bool]:
    direct: list[Expr] = []
    guard_atoms: list[Expr] = []
    unknown: list[str] = []

    for atom in atoms:
        if _is_direct_input_atom(atom, context):
            direct.append(atom)
            continue
        facts = _facts(atom, context)
        if facts.unknown and not (facts.input_derived or facts.state_derived):
            unknown.append(render_expr(atom))
        else:
            guard_atoms.append(atom)

    provisional = False
    input_value: dict[str, object] | None = None
    if direct:
        direct_expression = _combine(direct, "&")
        assert direct_expression is not None
        input_value = _input_pattern(
            direct_expression,
            context=context,
            line=line,
            provisional=False,
        )
    elif atoms and not unknown:
        expression = _combine(atoms, "&")
        assert expression is not None
        facts = _facts(expression, context)
        if facts.input_derived and not facts.state_derived and not facts.unknown:
            input_value = _input_pattern(
                expression,
                context=context,
                line=line,
                provisional=True,
            )
            guard_atoms = []
            provisional = True

    guard_terms = [
        _guard_term(atom, context=context, line=line)
        for atom in guard_atoms
    ]
    return input_value, guard_terms, unknown, provisional


def _case(
    *,
    case_id: str,
    input_pattern: Mapping[str, object] | None,
    guard_terms: Sequence[Mapping[str, object]],
    exact: Expr,
    fallback: bool,
    confidence: str,
    unclassified: Sequence[str] = (),
) -> dict[str, object]:
    return {
        "id": case_id,
        "input_pattern": None if input_pattern is None else dict(input_pattern),
        "guard_terms": [dict(item) for item in guard_terms],
        "guard": _aggregate_guard(guard_terms, exact_expression=exact if fallback else None),
        "exact_enabling_condition": {
            "expression": render_expr(exact),
            "proven_exact": not unclassified,
        },
        "fallback": fallback,
        "confidence": "unknown" if unclassified else confidence,
        "unclassified_conditions": list(unclassified),
    }


def _derive_from_discriminator(
    discriminator: object,
    *,
    context: object,
    transition_id: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    decision = discriminator.decision
    if len(decision.params) != len(discriminator.definition.args):
        return [], []

    substitutions = {
        parameter.name: argument
        for parameter, argument in zip(decision.params, discriminator.definition.args)
    }
    prior_conditions: list[tuple[Expr, int]] = []
    cases: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []

    for clause in decision.guards:
        value = _substitute(clause.value, substitutions)
        variant, _ = _variant(value)
        condition = (
            None
            if clause.condition is None
            else _substitute(clause.condition, substitutions)
        )
        matches = variant == discriminator.variant

        prior_expression = _combine([item[0] for item in prior_conditions], "|")
        priority_guard = (
            None if prior_expression is None else UnaryExpr("!", prior_expression)
        )

        if matches and condition is None:
            exact = BoolExpr(True) if priority_guard is None else priority_guard
            terms = [
                _guard_term(
                    exact,
                    context=context,
                    line=clause.line,
                    origin="fallback",
                    display="otherwise",
                    excluded_clause_lines=[item[1] for item in prior_conditions],
                )
            ]
            cases.append(
                _case(
                    case_id=f"{transition_id}:C{len(cases) + 1}",
                    input_pattern=None,
                    guard_terms=terms,
                    exact=exact,
                    fallback=True,
                    confidence="exact",
                )
            )
            break

        if matches and condition is not None:
            conjunctions = _to_dnf(condition)
            if conjunctions is None:
                diagnostics.append(
                    _warning(
                        _DECOMPOSITION_UNRESOLVED,
                        (
                            f"`{render_expr(condition)}` exceeds the bounded Enabling Case "
                            "decomposition limits. The exact condition is preserved without "
                            "inventing an Input/Guard split."
                        ),
                        clause.line,
                    )
                )
                conjunctions = [_flatten_and(condition)]

            for atoms in conjunctions:
                authored = _combine(atoms, "&")
                assert authored is not None
                input_value, authored_guards, unknown, provisional = (
                    _classify_authored_conjunction(
                        atoms,
                        context=context,
                        line=clause.line,
                    )
                )
                if provisional:
                    diagnostics.append(
                        _warning(
                            _PROVISIONAL_INPUT,
                            (
                                f"`{render_expr(authored)}` is input-derived, but its direct "
                                "Input Pattern or occurrence semantics cannot be proven. It is "
                                "retained provisionally on the Input side."
                            ),
                            clause.line,
                        )
                    )

                terms = list(authored_guards)
                if priority_guard is not None:
                    terms.append(
                        _guard_term(
                            priority_guard,
                            context=context,
                            line=clause.line,
                            origin="priority-exclusion",
                            excluded_clause_lines=[item[1] for item in prior_conditions],
                        )
                    )
                exact = (
                    authored
                    if priority_guard is None
                    else BinaryExpr("&", authored, priority_guard)
                )
                cases.append(
                    _case(
                        case_id=f"{transition_id}:C{len(cases) + 1}",
                        input_pattern=input_value,
                        guard_terms=terms,
                        exact=exact,
                        fallback=False,
                        confidence="provisional" if provisional else "exact",
                        unclassified=unknown,
                    )
                )

        if condition is not None:
            prior_conditions.append((condition, clause.line))

    return cases, diagnostics


def _fallback_case_from_legacy(
    transition: Mapping[str, object],
    *,
    context: object,
    transition_id: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if transition.get("synthesized_failure"):
        return [], []

    raw = str(transition.get("condition_raw") or transition.get("condition") or "")
    trigger = transition.get("trigger")
    guards = [str(item) for item in transition.get("guards", []) if str(item)]
    diagnostics: list[dict[str, object]] = []

    if raw == "otherwise":
        exact = BoolExpr(True)
        term = _guard_term(
            exact,
            context=context,
            line=int(transition.get("source", {}).get("line", 1)),
            origin="fallback",
            display="otherwise",
        )
        return [
            _case(
                case_id=f"{transition_id}:C1",
                input_pattern=None,
                guard_terms=[term],
                exact=exact,
                fallback=True,
                confidence="inferred",
            )
        ], diagnostics

    input_value: dict[str, object] | None = None
    confidence = "inferred"
    if isinstance(trigger, Mapping) and str(trigger.get("display") or ""):
        role = str(trigger.get("role") or "")
        provisional = role == "provisional-trigger"
        input_value = {
            "display": str(trigger.get("display") or ""),
            "expression": str(trigger.get("expression") or trigger.get("display") or ""),
            "kind": "provisional-input-pattern" if provisional else "direct-input-pattern",
            "origin": "provisional-input-pattern" if provisional else "authored-direct-input-pattern",
            "confidence": "provisional" if provisional else str(trigger.get("confidence") or "inferred"),
            "provenance_roots": list(trigger.get("provenance_roots") or []),
            "source_line": int(transition.get("source", {}).get("line", 1)),
        }
        confidence = "provisional" if provisional else "inferred"

    terms: list[dict[str, object]] = []
    for value in guards:
        try:
            expression = parse_expr(value)
        except Exception:
            continue
        terms.append(
            _guard_term(
                expression,
                context=context,
                line=int(transition.get("source", {}).get("line", 1)),
            )
        )

    try:
        exact = parse_expr(raw) if raw not in {"", "next"} else BoolExpr(True)
    except Exception:
        exact = BoolExpr(True)

    if input_value is None and not terms and raw in {"", "next"}:
        return [
            _case(
                case_id=f"{transition_id}:C1",
                input_pattern=None,
                guard_terms=[],
                exact=exact,
                fallback=False,
                confidence="inferred",
            )
        ], diagnostics

    return [
        _case(
            case_id=f"{transition_id}:C1",
            input_pattern=input_value,
            guard_terms=terms,
            exact=exact,
            fallback=False,
            confidence=confidence,
            unclassified=[
                str(item)
                for item in transition.get("unclassified_conditions", [])
                if str(item)
            ],
        )
    ], diagnostics


def _compatibility_projection(
    transition: dict[str, object],
    cases: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    result = dict(transition)
    diagnostics: list[dict[str, object]] = []
    result["enabling_cases"] = [dict(item) for item in cases]
    result["legacy_projection_lossy"] = len(cases) > 1

    if len(cases) > 1:
        diagnostics.append(
            _warning(
                _LEGACY_LOSSY,
                (
                    "Multiple Enabling Cases cannot be represented faithfully by the legacy "
                    "single trigger/guards fields. New renderers must consume enabling_cases."
                ),
                int(result.get("source", {}).get("line", 1)),
            )
        )
        return result, diagnostics

    if len(cases) != 1:
        return result, diagnostics

    case = cases[0]
    input_pattern = case.get("input_pattern")
    guard_terms = [
        dict(item)
        for item in case.get("guard_terms", [])
        if isinstance(item, Mapping)
    ]
    if isinstance(input_pattern, Mapping):
        role = (
            "provisional-trigger"
            if input_pattern.get("confidence") == "provisional"
            else "confirmed-trigger"
        )
        result["trigger"] = {
            "display": str(input_pattern.get("display") or ""),
            "expression": str(input_pattern.get("expression") or ""),
            "role": role,
            "confidence": str(input_pattern.get("confidence") or "unknown"),
            "provenance_roots": list(input_pattern.get("provenance_roots") or []),
            "provenance": str(input_pattern.get("origin") or ""),
        }
        result["event"] = str(input_pattern.get("display") or "")
    elif case.get("fallback"):
        result["trigger"] = None
        result["event"] = None

    result["guards"] = [str(item.get("display") or "") for item in guard_terms]
    guard = case.get("guard")
    result["guard"] = (
        str(guard.get("display") or "")
        if isinstance(guard, Mapping)
        else None
    )
    return result, diagnostics


def attach_machine_enabling_cases(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Attach source-preserving Input Pattern/Guard Enabling Cases to transitions."""

    result = deepcopy(machine_view)
    machine = next(
        (item for item in model.machines if item.name == result.get("name")),
        None,
    )
    if machine is None:
        return result

    definitions = _block_definitions(model, _next_name(machine))
    functions = {
        item.name: item
        for item in model.program.declarations
        if hasattr(item, "guards")
    }
    blocks = {item.name: item for item in model.blocks}
    lambdas = {item.name: item for item in model.lambdas}

    transitions: list[dict[str, object]] = []
    generated: list[dict[str, object]] = []
    exact_count = 0
    provisional_count = 0
    lossy_count = 0

    for index, original in enumerate(result.get("transitions", [])):
        transition = dict(original)
        transition_id = str(transition.get("id") or f"T{index + 1}")
        context = _context(
            model,
            machine,
            transition,
            products={
                item.name: item
                for item in model.program.declarations
                if item.__class__.__name__ == "ProductDecl"
            },
            sums={
                item.name: item
                for item in model.program.declarations
                if item.__class__.__name__ == "SumDecl"
            },
            functions=functions,
            externs={
                item.name: item
                for item in model.program.declarations
                if item.__class__.__name__ == "ExternDecl"
            },
            aliases={
                item.name: item.target
                for item in model.program.declarations
                if item.__class__.__name__ == "AliasDecl"
            },
        )

        cases: list[dict[str, object]] = []
        local_diagnostics: list[dict[str, object]] = []
        preimage = transition.get("input_preimage")
        raw = str(transition.get("condition_raw") or transition.get("condition") or "")
        if isinstance(preimage, Mapping) and definitions and raw not in {"", "otherwise", "next"}:
            try:
                condition = parse_expr(raw)
            except Exception:
                condition = None
            if condition is not None:
                candidates = _intermediate_discriminators(condition, definitions=definitions)
                if len(candidates) == 1:
                    discriminator = _resolve_discriminator(
                        candidates[0],
                        functions=functions,
                        blocks=blocks,
                        lambdas=lambdas,
                    )
                    if discriminator is not None:
                        cases, local_diagnostics = _derive_from_discriminator(
                            discriminator,
                            context=context,
                            transition_id=transition_id,
                        )

        if not cases:
            cases, fallback_diagnostics = _fallback_case_from_legacy(
                transition,
                context=context,
                transition_id=transition_id,
            )
            local_diagnostics.extend(fallback_diagnostics)

        projected, projection_diagnostics = _compatibility_projection(transition, cases)
        local_diagnostics.extend(projection_diagnostics)
        transitions.append(projected)
        generated.extend(local_diagnostics)

        exact_count += sum(
            1
            for item in cases
            if item.get("confidence") == "exact"
        )
        provisional_count += sum(
            1
            for item in cases
            if item.get("confidence") in {"provisional", "unknown"}
        )
        lossy_count += int(bool(projected.get("legacy_projection_lossy")))

    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
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
    analysis.update(
        {
            "enabling_case_version": ENABLING_CASE_VERSION,
            "enabling_case_count": sum(
                len(item.get("enabling_cases", [])) for item in transitions
            ),
            "exact_enabling_case_count": exact_count,
            "provisional_enabling_case_count": provisional_count,
            "lossy_legacy_projection_count": lossy_count,
        }
    )
    result["transitions"] = transitions
    result["diagnostics"] = diagnostics
    result["analysis"] = analysis
    return result


__all__ = [
    "ENABLING_CASE_VERSION",
    "MAX_CONDITION_ATOMS",
    "MAX_ENABLING_CASES",
    "attach_machine_enabling_cases",
]

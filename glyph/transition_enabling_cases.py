from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
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
    NumberExpr,
    TryExpr,
    UnaryExpr,
)
from .execution_ir import render_expr


ENABLING_CASES_VERSION = 1
STATE_TRANSITION_IR_VERSION = 5
_UNRESOLVED_CODE = "STIR_INPUT_GUARD_DECOMPOSITION_UNRESOLVED"
_MAX_CASES = 16
_MAX_ATOMS = 64


@dataclass(frozen=True)
class _CaseExpr:
    input_pattern: Expr | None
    authored_guards: tuple[Expr, ...]


def _variant(expr: Expr) -> str | None:
    if isinstance(expr, NameExpr):
        return expr.name
    if isinstance(expr, CallExpr) and isinstance(expr.callee, NameExpr):
        return expr.callee.name
    return None


def _substitute(expr: Expr, values: Mapping[str, Expr]) -> Expr:
    if isinstance(expr, NameExpr):
        return values.get(expr.name, expr)
    if isinstance(expr, FieldExpr):
        return FieldExpr(_substitute(expr.base, values), expr.field)
    if isinstance(expr, UnaryExpr):
        return UnaryExpr(expr.op, _substitute(expr.expr, values))
    if isinstance(expr, BinaryExpr):
        return BinaryExpr(
            expr.op,
            _substitute(expr.left, values),
            _substitute(expr.right, values),
        )
    if isinstance(expr, CallExpr):
        return CallExpr(
            _substitute(expr.callee, values),
            tuple(_substitute(argument, values) for argument in expr.args),
        )
    if isinstance(expr, TryExpr):
        return TryExpr(_substitute(expr.expr, values))
    return expr


def _flatten(expr: Expr, operator: str) -> list[Expr]:
    if isinstance(expr, BinaryExpr) and expr.op == operator:
        return [*_flatten(expr.left, operator), *_flatten(expr.right, operator)]
    return [expr]


def _combine(parts: Sequence[Expr], operator: str) -> Expr | None:
    iterator = iter(parts)
    try:
        result = next(iterator)
    except StopIteration:
        return None
    for part in iterator:
        result = BinaryExpr(operator, result, part)
    return result


def _input_roots(expr: Expr, input_names: frozenset[str]) -> set[str]:
    roots: set[str] = set()

    def visit(item: Expr) -> None:
        if isinstance(item, NameExpr):
            if item.name in input_names:
                roots.add(item.name)
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
            for argument in item.args:
                visit(argument)
            return
        if isinstance(item, TryExpr):
            visit(item.expr)

    visit(expr)
    return roots


def _contains_call(expr: Expr) -> bool:
    if isinstance(expr, CallExpr):
        return True
    if isinstance(expr, FieldExpr):
        return _contains_call(expr.base)
    if isinstance(expr, UnaryExpr):
        return _contains_call(expr.expr)
    if isinstance(expr, BinaryExpr):
        return _contains_call(expr.left) or _contains_call(expr.right)
    if isinstance(expr, TryExpr):
        return _contains_call(expr.expr)
    return False


def _is_literal(expr: Expr) -> bool:
    return isinstance(expr, (BoolExpr, NumberExpr, NameExpr))


def _is_direct_subject(expr: Expr, input_names: frozenset[str]) -> bool:
    if isinstance(expr, NameExpr):
        return expr.name in input_names
    if isinstance(expr, FieldExpr):
        return isinstance(expr.base, NameExpr) and expr.base.name in input_names
    return False


def _is_direct_input_atom(expr: Expr, input_names: frozenset[str]) -> bool:
    if isinstance(expr, UnaryExpr) and expr.op == "!":
        return _is_direct_subject(expr.expr, input_names)
    if _is_direct_subject(expr, input_names):
        return True
    if isinstance(expr, BinaryExpr) and expr.op in {"==", "!=", "<", "<=", ">", ">="}:
        return (
            _is_direct_subject(expr.left, input_names) and _is_literal(expr.right)
        ) or (
            _is_direct_subject(expr.right, input_names) and _is_literal(expr.left)
        )
    if isinstance(expr, BinaryExpr) and expr.op == "|":
        return all(_is_direct_input_atom(part, input_names) for part in _flatten(expr, "|"))
    return False


def _guard_origin(expr: Expr, state_name: str, input_names: frozenset[str]) -> str:
    rendered = render_expr(expr)
    if state_name and (rendered == state_name or rendered.startswith(f"{state_name}.")):
        return "state-condition"
    if _contains_call(expr) and _input_roots(expr, input_names):
        return "authored-derived-predicate"
    if _input_roots(expr, input_names):
        return "authored-derived-predicate"
    return "unknown"


def _decompose_conjunction(
    expr: Expr,
    *,
    input_names: frozenset[str],
) -> _CaseExpr:
    input_parts: list[Expr] = []
    guard_parts: list[Expr] = []
    for atom in _flatten(expr, "&"):
        if _is_direct_input_atom(atom, input_names):
            input_parts.append(atom)
        else:
            guard_parts.append(atom)
    return _CaseExpr(
        input_pattern=_combine(input_parts, "&"),
        authored_guards=tuple(guard_parts),
    )


def _dnf_cases(
    expr: Expr,
    *,
    input_names: frozenset[str],
) -> list[_CaseExpr] | None:
    disjuncts = _flatten(expr, "|")
    atom_count = sum(len(_flatten(item, "&")) for item in disjuncts)
    if len(disjuncts) > _MAX_CASES or atom_count > _MAX_ATOMS:
        return None
    return [
        _decompose_conjunction(item, input_names=input_names)
        for item in disjuncts
    ]


def _input_object(expr: Expr | None, input_names: frozenset[str]) -> dict[str, object] | None:
    if expr is None:
        return None
    display = render_expr(expr)
    roots = sorted(f"input:{name}" for name in _input_roots(expr, input_names))
    return {
        "display": display,
        "expression": display,
        "kind": "direct-input-pattern",
        "confidence": "exact",
        "provenance_roots": roots,
        "source_origin": "authored-clause",
    }


def _guard_object(
    authored: Sequence[Expr],
    *,
    priority: Expr | None,
    fallback: bool,
    state_name: str,
    input_names: frozenset[str],
) -> dict[str, object] | None:
    terms: list[dict[str, object]] = []
    for expr in authored:
        value = render_expr(expr)
        terms.append(
            {
                "display": value,
                "expression": value,
                "origin": _guard_origin(expr, state_name, input_names),
            }
        )
    if priority is not None:
        value = render_expr(priority)
        terms.append(
            {
                "display": value,
                "expression": value,
                "origin": "priority-exclusion",
            }
        )
    if fallback:
        terms.insert(
            0,
            {
                "display": "otherwise",
                "expression": "otherwise",
                "origin": "fallback",
            },
        )
    if not terms:
        return None
    display_terms = [str(item["display"]) for item in terms if item["origin"] != "fallback"]
    display = "otherwise" if fallback else "&".join(display_terms)
    expression_terms = [
        str(item["expression"])
        for item in terms
        if item["origin"] != "fallback"
    ]
    return {
        "display": display,
        "expression": "&".join(expression_terms) or "true",
        "terms": terms,
    }


def _warning(message: str, line: int) -> dict[str, object]:
    return {
        "severity": "warning",
        "code": _UNRESOLVED_CODE,
        "message": message,
        "line": line,
    }


def _decision_substitutions(
    decision: FunctionDecl,
    machine_input_names: Sequence[str],
) -> dict[str, Expr] | None:
    if len(decision.params) > len(machine_input_names):
        return None
    values: dict[str, Expr] = {}
    for parameter, machine_name in zip(decision.params, machine_input_names):
        values[parameter.name] = NameExpr(machine_name)
    return values


def _action_variant(transition: Mapping[str, object]) -> str:
    action = transition.get("action")
    if not isinstance(action, Mapping):
        return ""
    return str(action.get("variant") or "").strip()


def _build_cases(
    transition: Mapping[str, object],
    *,
    decision: FunctionDecl,
    substitutions: Mapping[str, Expr],
    input_names: frozenset[str],
    state_name: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    wanted = _action_variant(transition)
    prior_different: list[Expr] = []
    cases: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    transition_id = str(transition.get("id") or "T")

    for clause in decision.guards:
        value = _substitute(clause.value, substitutions)
        condition = None if clause.condition is None else _substitute(clause.condition, substitutions)
        matches = _variant(value) == wanted
        if not matches:
            if condition is not None:
                prior_different.append(condition)
            continue

        prior_expr = _combine(prior_different, "|")
        priority = None if prior_expr is None else UnaryExpr("!", prior_expr)
        fallback = condition is None
        if fallback:
            decomposed = [_CaseExpr(None, ())]
            exact = BoolExpr(True) if priority is None else priority
        else:
            decomposed = _dnf_cases(condition, input_names=input_names)
            if decomposed is None:
                line = int(getattr(clause, "line", 1) or 1)
                diagnostics.append(
                    _warning(
                        f"`{render_expr(condition)}` exceeds bounded Input/Guard decomposition; "
                        "the authored expression is retained provisionally without dropping semantics.",
                        line,
                    )
                )
                decomposed = [_CaseExpr(condition, ())]
            exact = condition if priority is None else BinaryExpr("&", condition, priority)

        for item in decomposed:
            authored_expr = item.input_pattern
            if item.authored_guards:
                guard_expr = _combine(item.authored_guards, "&")
                authored_expr = (
                    guard_expr
                    if authored_expr is None
                    else BinaryExpr("&", authored_expr, guard_expr)
                )
            exact_case = exact if len(decomposed) == 1 else (
                authored_expr
                if priority is None
                else BinaryExpr("&", authored_expr, priority)
            )
            case_id = f"{transition_id}:C{len(cases) + 1}"
            input_object = _input_object(item.input_pattern, input_names)
            guard_object = _guard_object(
                item.authored_guards,
                priority=priority,
                fallback=fallback,
                state_name=state_name,
                input_names=input_names,
            )
            exact_display = render_expr(exact_case)
            cases.append(
                {
                    "id": case_id,
                    "input_pattern": input_object,
                    "guard": guard_object,
                    "enabling_condition": {
                        "display": exact_display,
                        "expression": exact_display,
                        "proven_exact": True,
                    },
                    "fallback": fallback,
                    "confidence": "exact" if not diagnostics else "fallback",
                    "source": {
                        "line": int(getattr(clause, "line", 1) or 1),
                        "origin": "authored-clause",
                    },
                }
            )
    return cases, diagnostics


def _legacy_projection(transition: dict[str, object]) -> None:
    cases = transition.get("enabling_cases")
    if not isinstance(cases, list) or not cases:
        return
    first = cases[0]
    input_pattern = first.get("input_pattern") if isinstance(first, Mapping) else None
    guard = first.get("guard") if isinstance(first, Mapping) else None
    if isinstance(input_pattern, Mapping):
        transition["trigger"] = {
            "display": input_pattern.get("display"),
            "expression": input_pattern.get("expression"),
            "role": "inferred-trigger",
            "confidence": input_pattern.get("confidence", "exact"),
            "provenance": "enabling-case-input-pattern",
            "provenance_roots": list(input_pattern.get("provenance_roots", [])),
        }
        transition["event"] = str(input_pattern.get("display") or "")
    else:
        transition["trigger"] = None
        transition["event"] = None
    guard_terms = []
    if isinstance(guard, Mapping):
        guard_terms = [
            str(item.get("display") or "")
            for item in guard.get("terms", [])
            if isinstance(item, Mapping) and item.get("display")
        ]
    transition["guards"] = guard_terms
    transition["guard"] = "&".join(guard_terms) or None
    transition["legacy_projection_lossy"] = len(cases) != 1


def attach_machine_enabling_cases(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
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
    input_names_ordered = [parameter.name for parameter in machine.input_params]
    input_names = frozenset(input_names_ordered)
    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
    transitions: list[dict[str, object]] = []
    case_count = 0
    lossy_count = 0

    for original in result.get("transitions", []):
        transition = dict(original)
        preimage = transition.get("input_preimage")
        decision_name = (
            str(preimage.get("decision_function") or "")
            if isinstance(preimage, Mapping)
            else ""
        )
        decision = functions.get(decision_name)
        if decision is None:
            transitions.append(transition)
            continue
        substitutions = _decision_substitutions(decision, input_names_ordered)
        if substitutions is None:
            transitions.append(transition)
            continue
        cases, generated = _build_cases(
            transition,
            decision=decision,
            substitutions=substitutions,
            input_names=input_names,
            state_name=machine.state_param.name,
        )
        if cases:
            transition["enabling_cases"] = cases
            _legacy_projection(transition)
            case_count += len(cases)
            lossy_count += int(bool(transition.get("legacy_projection_lossy")))
        diagnostics.extend(generated)
        transitions.append(transition)

    analysis = dict(result.get("analysis", {}))
    analysis["enabling_cases_version"] = ENABLING_CASES_VERSION
    analysis["enabling_case_count"] = case_count
    analysis["lossy_legacy_projection_count"] = lossy_count
    result["transitions"] = transitions
    result["diagnostics"] = diagnostics
    result["analysis"] = analysis
    return result


__all__ = [
    "ENABLING_CASES_VERSION",
    "STATE_TRANSITION_IR_VERSION",
    "attach_machine_enabling_cases",
]

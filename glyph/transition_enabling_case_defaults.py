from __future__ import annotations

from copy import deepcopy
from typing import Mapping


ENABLING_CASE_SOURCE = "classified-transition"


def _text(value: object) -> str:
    return str(value or "").strip()


def _trigger_input(trigger: object) -> dict[str, object] | None:
    if not isinstance(trigger, Mapping):
        return None
    display = _text(trigger.get("display") or trigger.get("expression"))
    if not display:
        return None
    return {
        "display": display,
        "expression": _text(trigger.get("expression")) or display,
        "kind": (
            "provisional-input-pattern"
            if trigger.get("role") == "provisional-trigger"
            else "classified-input-pattern"
        ),
        "confidence": _text(trigger.get("confidence")) or "fallback",
        "provenance_roots": list(trigger.get("provenance_roots", [])),
        "source_origin": ENABLING_CASE_SOURCE,
    }


def _guard_from_transition(transition: Mapping[str, object]) -> dict[str, object] | None:
    guards = [
        _text(item)
        for item in transition.get("guards", [])
        if _text(item)
    ]
    unknown = [
        _text(item)
        for item in transition.get("unclassified_conditions", [])
        if _text(item)
    ]
    terms: list[dict[str, object]] = []
    for value in guards:
        terms.append(
            {
                "display": value,
                "expression": value,
                "origin": (
                    "state-condition"
                    if "state." in value
                    else "authored-derived-predicate"
                ),
            }
        )
    for value in unknown:
        terms.append(
            {
                "display": f"? {value}",
                "expression": value,
                "origin": "unknown",
            }
        )
    if not terms:
        return None
    return {
        "display": "&".join(_text(item["display"]) for item in terms),
        "expression": "&".join(_text(item["expression"]) for item in terms),
        "terms": terms,
    }


def _fallback_case(transition: Mapping[str, object]) -> dict[str, object]:
    transition_id = _text(transition.get("id")) or "T"
    raw = _text(transition.get("condition_raw") or transition.get("condition"))
    exact = raw if raw and raw not in {"otherwise", "next"} else "true"
    return {
        "id": f"{transition_id}:C1",
        "input_pattern": None,
        "guard": {
            "display": "otherwise",
            "expression": "true",
            "terms": [
                {
                    "display": "otherwise",
                    "expression": "otherwise",
                    "origin": "fallback",
                }
            ],
        },
        "enabling_condition": {
            "display": exact,
            "expression": exact,
            "proven_exact": raw in {"", "otherwise", "next"},
        },
        "fallback": True,
        "confidence": "exact" if raw in {"", "otherwise", "next"} else "fallback",
        "source": {
            "line": int((transition.get("source") or {}).get("line", 1)),
            "origin": ENABLING_CASE_SOURCE,
        },
    }


def _classified_case(transition: Mapping[str, object]) -> dict[str, object]:
    transition_id = _text(transition.get("id")) or "T"
    input_pattern = _trigger_input(transition.get("trigger"))
    guard = _guard_from_transition(transition)
    input_expression = (
        _text(input_pattern.get("expression"))
        if isinstance(input_pattern, Mapping)
        else ""
    )
    guard_expression = (
        _text(guard.get("expression"))
        if isinstance(guard, Mapping)
        else ""
    )
    parts = [item for item in (input_expression, guard_expression) if item]
    raw = _text(transition.get("condition_raw") or transition.get("condition"))
    exact = raw or "&".join(parts) or "true"
    confidence = (
        _text(input_pattern.get("confidence"))
        if isinstance(input_pattern, Mapping)
        else "exact"
    )
    return {
        "id": f"{transition_id}:C1",
        "input_pattern": input_pattern,
        "guard": guard,
        "enabling_condition": {
            "display": exact,
            "expression": exact,
            "proven_exact": bool(raw) or bool(parts),
        },
        "fallback": False,
        "confidence": confidence or "fallback",
        "source": {
            "line": int((transition.get("source") or {}).get("line", 1)),
            "origin": ENABLING_CASE_SOURCE,
        },
    }


def ensure_machine_enabling_cases(
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Give every transition an enabling-case representation without string inference in UI."""

    result = deepcopy(machine_view)
    transitions: list[dict[str, object]] = []
    case_count = 0
    for original in result.get("transitions", []):
        transition = dict(original)
        cases = transition.get("enabling_cases")
        if not isinstance(cases, list) or not cases:
            raw = _text(transition.get("condition_raw") or transition.get("condition"))
            has_semantic_condition = bool(
                transition.get("trigger")
                or transition.get("guards")
                or transition.get("unclassified_conditions")
            )
            case = (
                _classified_case(transition)
                if has_semantic_condition
                else _fallback_case(transition)
            )
            transition["enabling_cases"] = [case]
            transition["legacy_projection_lossy"] = False
            cases = transition["enabling_cases"]
        case_count += len(cases)
        transitions.append(transition)

    analysis = dict(result.get("analysis", {}))
    analysis["enabling_case_count"] = case_count
    analysis["all_transitions_have_enabling_cases"] = all(
        bool(item.get("enabling_cases")) for item in transitions
    )
    result["transitions"] = transitions
    result["analysis"] = analysis
    return result


__all__ = ["ensure_machine_enabling_cases"]

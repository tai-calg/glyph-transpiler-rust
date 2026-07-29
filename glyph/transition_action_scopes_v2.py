from __future__ import annotations

from copy import deepcopy
from typing import Mapping, Sequence

from ._transition_action_ir import renumber_invocations, text


_CONTEXT_REQUIRED_CODE = "STIR_SYSTEM_ACTION_CONTEXT_REQUIRED"
_DISPLAY_PROJECTION_PROVENANCE = "transition-display-action-projection"
_BLOCKING_STATUSES = {"unresolved", "multiple-transition-calls"}


def _invocations(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _action_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return text(value.get("display")) or text(value.get("expression"))
    return ""


def _case_signature(case: Mapping[str, object]) -> tuple[object, ...]:
    return (
        text(case.get("condition")),
        text(case.get("status")),
        text(case.get("outcome")),
        bool(case.get("reaches_continuation", True)),
        tuple(
            (text(item.get("expression")), item.get("failure_type"))
            for item in _invocations(case.get("action_invocations", []))
        ),
    )


def _binding_signature(binding: Mapping[str, object]) -> tuple[object, ...]:
    cases = binding.get("action_cases", [])
    case_signature = (
        tuple(_case_signature(item) for item in cases if isinstance(item, Mapping))
        if isinstance(cases, Sequence) and not isinstance(cases, (str, bytes))
        else ()
    )
    return (
        text(binding.get("status")) or "resolved",
        _action_text(binding.get("action")),
        tuple(
            (text(item.get("expression")), item.get("failure_type"))
            for item in _invocations(binding.get("action_invocations", []))
        ),
        case_signature,
    )


def _context_invocations(context: Mapping[str, object]) -> list[dict[str, object]]:
    cases = context.get("action_cases", [])
    if isinstance(cases, Sequence) and not isinstance(cases, (str, bytes)):
        flattened = [
            dict(item)
            for case in cases
            if isinstance(case, Mapping)
            for item in _invocations(case.get("action_invocations", []))
        ]
        if flattened:
            return flattened
    return _invocations(context.get("action_invocations", []))


def _diagnostic(message: str, line: int) -> dict[str, object]:
    return {
        "severity": "warning",
        "code": _CONTEXT_REQUIRED_CODE,
        "message": message,
        "line": line,
    }


def _append_once(
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


def _composed_action(
    machine_action: object,
    execution_action: object,
    *,
    scope: str,
    systems: Sequence[str],
    entries: Sequence[str],
) -> dict[str, object] | None:
    parts = [_action_text(machine_action), _action_text(execution_action)]
    parts = [item for item in parts if item]
    if not parts:
        return None
    display = "; ".join(parts)
    result = {
        "display": display,
        "expression": display,
        "operation": None,
        "operations": [],
        "kind": "operation-invocation" if len(parts) == 1 else "operation-sequence",
        "effectful": True,
        "provenance": "transition-operation-invocation",
        "projection_provenance": _DISPLAY_PROJECTION_PROVENANCE,
        "scope": scope,
        "systems": list(systems),
        "entries": list(entries),
        "source": {"line": 1, "column": 1},
    }
    if isinstance(machine_action, Mapping) and machine_action.get("source"):
        result["source"] = deepcopy(machine_action.get("source"))
    elif isinstance(execution_action, Mapping) and execution_action.get("source"):
        result["source"] = deepcopy(execution_action.get("source"))
    return result


def project_transition_action_scopes(
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Project display Actions only when every applicable context is represented.

    `execution_contexts` is the complete set, including actionless and unresolved
    contexts. `execution_action_bindings` remains a compatibility subset containing
    only resolved contexts that actually publish an Action.
    """

    result = deepcopy(machine_view)
    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
    transitions: list[dict[str, object]] = []
    context_required_count = 0
    projected_count = 0
    result_dependent_count = 0
    sequenced_count = 0

    for original in result.get("transitions", []):
        transition = dict(original)
        # Finalization immediately before this stage specializes branch-local values.
        machine_action = deepcopy(transition.get("action"))
        machine_invocations = _invocations(transition.get("action_invocations", []))
        machine_effects = _invocations(transition.get("effect_invocations", []))
        transition["machine_action"] = machine_action
        transition["machine_action_invocations"] = [dict(item) for item in machine_invocations]
        transition["machine_effect_invocations"] = [dict(item) for item in machine_effects]

        contexts = [
            dict(item)
            for item in transition.get(
                "execution_contexts",
                transition.get("execution_action_bindings", []),
            )
            if isinstance(item, Mapping)
        ]
        transition["execution_contexts"] = contexts
        transition["execution_action_bindings"] = [
            dict(item)
            for item in contexts
            if text(item.get("status")) not in _BLOCKING_STATUSES
            and item.get("action") is not None
        ]

        for context in contexts:
            for invocation in _context_invocations(context):
                relation = invocation.get("execution_relation")
                if relation == "result-dependency":
                    result_dependent_count += 1
                elif relation == "post-transition-control":
                    sequenced_count += 1

        source = transition.get("source", {})
        line = int(source.get("line", 1)) if isinstance(source, Mapping) else 1
        statuses = [text(item.get("status")) or "resolved" for item in contexts]
        blocking = any(status in _BLOCKING_STATUSES for status in statuses)
        signatures: dict[tuple[object, ...], list[dict[str, object]]] = {}
        for context in contexts:
            signatures.setdefault(_binding_signature(context), []).append(context)

        context_required = blocking or len(signatures) > 1
        selected_contexts: list[dict[str, object]] = []
        representative: dict[str, object] | None = None
        if contexts and not context_required and len(signatures) == 1:
            selected_contexts = next(iter(signatures.values()))
            representative = selected_contexts[0]

        if context_required:
            context_required_count += 1
            names = [
                f"{item.get('system') or 'implicit'} / {item.get('entry') or '?'}"
                f" ({item.get('status') or 'resolved'})"
                for item in contexts
            ]
            _append_once(
                diagnostics,
                _diagnostic(
                    (
                        "machine transition has incomplete or different system execution "
                        f"contexts for {', '.join(names)}; select one context explicitly"
                    ),
                    line,
                ),
            )

        execution_action = representative.get("action") if representative else None
        execution_invocations = (
            _invocations(representative.get("action_invocations", []))
            if representative
            else []
        )
        execution_effects = (
            _invocations(representative.get("effect_invocations", []))
            if representative
            else []
        )
        systems = sorted(
            {
                str(item.get("system"))
                for item in selected_contexts
                if item.get("system")
            }
        )
        entries = sorted(
            {
                str(item.get("entry"))
                for item in selected_contexts
                if item.get("entry")
            }
        )
        display_scope = (
            "composed"
            if machine_action is not None and execution_action is not None
            else "system"
            if execution_action is not None
            else "machine"
            if machine_action is not None
            else "none"
        )
        display_action = _composed_action(
            machine_action,
            execution_action,
            scope=display_scope,
            systems=systems,
            entries=entries,
        )
        display_invocations = renumber_invocations(
            [*machine_invocations, *execution_invocations]
        )
        display_effects = renumber_invocations([*machine_effects, *execution_effects])
        if display_action is not None:
            projected_count += 1

        status_counts: dict[str, int] = {}
        for status in statuses:
            status_counts[status] = status_counts.get(status, 0) + 1

        transition["display_action"] = display_action
        transition["display_action_invocations"] = display_invocations
        transition["display_effect_invocations"] = display_effects
        transition["action_scope"] = {
            "machine": bool(machine_action),
            "execution_context_count": len(contexts),
            "selected_context_count": len(selected_contexts),
            "display_scope": display_scope,
            "systems": systems,
            "entries": entries,
            "context_required": context_required,
            "context_status_counts": status_counts,
        }
        transition["action"] = deepcopy(display_action)
        transition["action_invocations"] = [dict(item) for item in display_invocations]
        transition["effect_invocations"] = [dict(item) for item in display_effects]
        transitions.append(transition)

    analysis = dict(result.get("analysis", {}))
    analysis.update(
        {
            "transition_action_scope_version": 1,
            "transition_execution_context_projection_version": 1,
            "display_action_transition_count": projected_count,
            "system_action_context_required_count": context_required_count,
            "execution_action_result_dependent_count": result_dependent_count,
            "execution_action_sequenced_count": sequenced_count,
        }
    )
    result["transitions"] = transitions
    result["diagnostics"] = diagnostics
    result["analysis"] = analysis
    return result


__all__ = ["project_transition_action_scopes"]

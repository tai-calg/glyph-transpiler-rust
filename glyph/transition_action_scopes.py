from __future__ import annotations

from copy import deepcopy
from typing import Mapping, Sequence

from ._transition_action_ir import build_operation_action, renumber_invocations, text


_CONTEXT_REQUIRED_CODE = "STIR_SYSTEM_ACTION_CONTEXT_REQUIRED"
_DISPLAY_PROVENANCE = "transition-display-action-projection"


def _invocations(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _sequence_key(
    invocations: Sequence[Mapping[str, object]],
) -> tuple[tuple[str, object], ...]:
    return tuple(
        (text(item.get("expression")), item.get("failure_type"))
        for item in invocations
    )


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


def _display_action(
    machine_invocations: Sequence[Mapping[str, object]],
    execution_invocations: Sequence[Mapping[str, object]],
    *,
    scope: str,
    systems: Sequence[str],
    entries: Sequence[str],
) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    combined = renumber_invocations(
        [*machine_invocations, *execution_invocations]
    )
    action = build_operation_action(combined)
    if action is not None:
        action["provenance"] = _DISPLAY_PROVENANCE
        action["scope"] = scope
        action["systems"] = list(systems)
        action["entries"] = list(entries)
    return action, combined


def project_transition_action_scopes(
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Publish intrinsic, execution-context, and renderer Action axes.

    ``machine_action`` belongs to the reusable machine transition.
    ``execution_action_bindings`` belong to concrete system entries.
    ``display_action`` is a view projection only. The compatibility fields
    ``action`` and ``action_invocations`` mirror that projection for older
    consumers and carry explicit projection provenance.
    """

    result = deepcopy(machine_view)
    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
    transitions: list[dict[str, object]] = []
    divergent_count = 0
    projected_count = 0

    for original in result.get("transitions", []):
        transition = dict(original)
        machine_action = deepcopy(transition.get("action"))
        machine_invocations = _invocations(transition.get("action_invocations", []))
        machine_effects = _invocations(transition.get("effect_invocations", []))
        transition["machine_action"] = machine_action
        transition["machine_action_invocations"] = [
            dict(item) for item in machine_invocations
        ]
        transition["machine_effect_invocations"] = [
            dict(item) for item in machine_effects
        ]

        bindings = [
            dict(item)
            for item in transition.get("execution_action_bindings", [])
            if isinstance(item, Mapping)
        ]
        by_sequence: dict[
            tuple[tuple[str, object], ...],
            list[dict[str, object]],
        ] = {}
        for binding in bindings:
            key = _sequence_key(_invocations(binding.get("action_invocations", [])))
            by_sequence.setdefault(key, []).append(binding)

        source = transition.get("source", {})
        line = int(source.get("line", 1)) if isinstance(source, Mapping) else 1
        selected_bindings: list[dict[str, object]] = []
        execution_invocations: list[dict[str, object]] = []
        display_scope = "machine" if machine_invocations else "none"

        if len(by_sequence) == 1:
            selected_bindings = next(iter(by_sequence.values()))
            representative = selected_bindings[0]
            execution_invocations = _invocations(
                representative.get("action_invocations", [])
            )
            display_scope = "composed" if machine_invocations else "system"
        elif len(by_sequence) > 1:
            divergent_count += 1
            systems = [
                str(item.get("system") or item.get("entry") or "unknown")
                for item in bindings
            ]
            _append_once(
                diagnostics,
                _diagnostic(
                    (
                        "machine transition has different system-entry Actions "
                        f"for {', '.join(systems)}; select an execution context "
                        "instead of treating a system operation as machine Action"
                    ),
                    line,
                ),
            )

        systems = sorted(
            {
                str(item.get("system"))
                for item in selected_bindings
                if item.get("system")
            }
        )
        entries = sorted(
            {
                str(item.get("entry"))
                for item in selected_bindings
                if item.get("entry")
            }
        )
        display_action, display_invocations = _display_action(
            machine_invocations,
            execution_invocations,
            scope=display_scope,
            systems=systems,
            entries=entries,
        )
        display_effects = renumber_invocations(
            [
                *machine_effects,
                *(
                    _invocations(
                        selected_bindings[0].get("effect_invocations", [])
                    )
                    if selected_bindings
                    else []
                ),
            ]
        )
        if display_action is not None:
            projected_count += 1

        transition["display_action"] = display_action
        transition["display_action_invocations"] = display_invocations
        transition["display_effect_invocations"] = display_effects
        transition["action_scope"] = {
            "machine": bool(machine_invocations),
            "execution_context_count": len(bindings),
            "selected_context_count": len(selected_bindings),
            "display_scope": display_scope,
            "systems": systems,
            "entries": entries,
            "context_required": len(by_sequence) > 1,
        }

        # Compatibility projection for existing renderer/API consumers.
        transition["action"] = deepcopy(display_action)
        transition["action_invocations"] = [
            dict(item) for item in display_invocations
        ]
        transition["effect_invocations"] = [dict(item) for item in display_effects]
        transitions.append(transition)

    analysis = dict(result.get("analysis", {}))
    analysis.update(
        {
            "transition_action_scope_version": 1,
            "display_action_transition_count": projected_count,
            "system_action_context_required_count": divergent_count,
        }
    )
    result["transitions"] = transitions
    result["diagnostics"] = diagnostics
    result["analysis"] = analysis
    return result


__all__ = ["project_transition_action_scopes"]

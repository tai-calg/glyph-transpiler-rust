from __future__ import annotations

from copy import deepcopy
from typing import Sequence


def _base_action(action: object, failure_type: object) -> str:
    rendered = str(action or "")
    suffix = f" ! {str(failure_type or '').strip()}"
    return rendered[: -len(suffix)] if suffix.strip() and rendered.endswith(suffix) else rendered


def _display_label(event: object, guard: object, action: str) -> str:
    event_text = str(event or "").strip()
    guard_text = str(guard or "").strip()
    label = event_text
    if guard_text:
        label += f" [{guard_text}]" if label else f"[{guard_text}]"
    if action:
        label += f" / {action}" if label else f"/ {action}"
    return label


def _reachable(initial: str, transitions: Sequence[dict[str, object]]) -> set[str]:
    reachable = {initial}
    changed = True
    while changed:
        changed = False
        for transition in transitions:
            source = str(transition.get("source_state", ""))
            target = str(transition.get("target_state", ""))
            if source in reachable and target not in reachable:
                reachable.add(target)
                changed = True
    return reachable


def restore_guard_distinct_failures(views: dict[str, object]) -> dict[str, object]:
    """Restore failure edges that differ only by event or guard.

    The semantic pass historically deduplicated synthesized effect failures by
    source state, failure state, action call, and error type. Two branches such as
    `input.overheat` and `!input.enable` can invoke the same effect from the same
    state, so that key incorrectly collapsed one valid failure path. This repair
    uses event and guard as part of transition identity and clones only a proven
    failure template for the same source state and effect call.
    """

    result = deepcopy(views)
    for machine in result.get("state", {}).get("machines", []):
        transitions = [dict(item) for item in machine.get("transitions", [])]
        failure_state = str(machine.get("failure_state", ""))
        templates: dict[tuple[str, str], list[dict[str, object]]] = {}
        existing: set[tuple[str, str, str, str, str, str]] = set()

        for transition in transitions:
            if not transition.get("synthesized_failure"):
                continue
            failure_type = str(transition.get("failure_type", "")).strip()
            if not failure_type:
                continue
            source = str(transition.get("source_state", ""))
            target = str(transition.get("target_state", failure_state))
            action = _base_action(transition.get("action"), failure_type)
            event = str(transition.get("event") or "")
            guard = str(transition.get("guard") or "")
            templates.setdefault((source, action), []).append(transition)
            existing.add((source, target, event, guard, action, failure_type))

        additions: list[dict[str, object]] = []
        for transition in transitions:
            if transition.get("synthesized_failure") or transition.get("outcome") == "failure":
                continue
            source = str(transition.get("source_state", ""))
            event = str(transition.get("event") or "")
            guard = str(transition.get("guard") or "")
            action_text = str(transition.get("action") or "")
            for action in filter(None, (item.strip() for item in action_text.split(";"))):
                for template in templates.get((source, action), []):
                    failure_type = str(template.get("failure_type", "")).strip()
                    target = failure_state or str(template.get("target_state", ""))
                    key = (source, target, event, guard, action, failure_type)
                    if key in existing:
                        continue
                    existing.add(key)
                    failure_action = f"{action} ! {failure_type}"
                    failure = dict(template)
                    failure.update(
                        {
                            "source_state": source,
                            "target_state": target,
                            "condition": transition.get("condition"),
                            "condition_raw": transition.get("condition_raw"),
                            "event": transition.get("event"),
                            "guard": transition.get("guard"),
                            "action": failure_action,
                            "display_label": _display_label(
                                transition.get("event"),
                                transition.get("guard"),
                                failure_action,
                            ),
                            "source": deepcopy(transition.get("source")),
                            "source_reachable": transition.get("source_reachable", True),
                            "expanded_from_wildcard": transition.get(
                                "expanded_from_wildcard", False
                            ),
                        }
                    )
                    additions.append(failure)

        if not additions:
            continue
        transitions.extend(additions)
        machine["transitions"] = transitions

        initial = str(machine.get("initial_state", ""))
        reachable = _reachable(initial, transitions)
        state_names = [str(state.get("name", "")) for state in machine.get("states", [])]
        machine["unreachable_states"] = [name for name in state_names if name not in reachable]
        for state in machine.get("states", []):
            state["reachable"] = str(state.get("name", "")) in reachable

        analysis = dict(machine.get("analysis", {}))
        analysis["normalized_transition_count"] = len(transitions)
        analysis["reachable_state_count"] = len(reachable)
        analysis["failure_transition_count"] = sum(
            1 for item in transitions if item.get("outcome") == "failure"
        )
        analysis["synthesized_failure_transition_count"] = sum(
            1 for item in transitions if item.get("synthesized_failure")
        )
        analysis["guard_distinct_failure_repair_count"] = len(additions)
        machine["analysis"] = analysis

    return result

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence


ANALYSIS_VERSION = 1
_TYPE_ALIAS_CODE = "STIR_ACTION_TARGET_TYPE_ALIAS"
_NEAR_ALIAS_CODE = "STIR_ACTION_TARGET_NEAR_ALIAS"
_REDUNDANT_AXIS_CODE = "STIR_ACTION_TARGET_REDUNDANT_AXIS"
_ROLE_WORDS = {
    "action",
    "command",
    "cmd",
    "operation",
    "op",
    "state",
    "mode",
    "status",
}


def _action_variant(transition: Mapping[str, object]) -> str:
    action = transition.get("action")
    if not isinstance(action, Mapping):
        return ""
    variant = str(action.get("variant") or "").strip()
    if variant:
        return variant
    display = str(action.get("display") or action.get("expression") or "").strip()
    open_pos = display.find("(")
    return display[:open_pos] if open_pos > 0 else display


def _source_line(transition: Mapping[str, object]) -> int:
    source = transition.get("source")
    if not isinstance(source, Mapping):
        return 1
    try:
        return max(1, int(source.get("line", 1)))
    except (TypeError, ValueError):
        return 1


def _split_identifier(value: str) -> list[str]:
    base = value.split("(", 1)[0]
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", base)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    return [item.lower() for item in re.split(r"[^A-Za-z0-9]+", spaced) if item]


def _stem_token(token: str) -> str:
    value = token.lower()
    if len(value) > 4 and value.endswith("ies"):
        value = f"{value[:-3]}y"
    elif len(value) > 5 and value.endswith("ing"):
        value = value[:-3]
    elif len(value) > 4 and value.endswith("ed"):
        value = value[:-2]
    elif len(value) > 3 and value.endswith("s") and not value.endswith("ss"):
        value = value[:-1]
    if len(value) > 3 and len(value) >= 2 and value[-1] == value[-2]:
        value = value[:-1]
    if len(value) > 4 and value.endswith("e"):
        value = value[:-1]
    return value


def semantic_name_key(value: str) -> tuple[str, ...]:
    tokens = [
        _stem_token(token)
        for token in _split_identifier(value)
        if token not in _ROLE_WORDS
    ]
    return tuple(sorted(token for token in tokens if token))


def _diagnostic(code: str, message: str, line: int) -> dict[str, object]:
    return {
        "severity": "warning",
        "code": code,
        "message": message,
        "line": line,
    }


def analyze_action_target_independence(
    transitions: Sequence[Mapping[str, object]],
    *,
    action_type: str | None,
    state_type: str | None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    pairs: list[tuple[str, str, int]] = []
    for transition in transitions:
        if transition.get("synthesized_failure"):
            continue
        action = _action_variant(transition)
        target = str(transition.get("target_state") or "").strip()
        if action and target:
            pairs.append((action, target, _source_line(transition)))

    action_to_targets: dict[str, set[str]] = defaultdict(set)
    target_to_actions: dict[str, set[str]] = defaultdict(set)
    for action, target, _ in pairs:
        action_to_targets[action].add(target)
        target_to_actions[target].add(action)

    action_witnesses = {
        action: sorted(targets)
        for action, targets in action_to_targets.items()
        if len(targets) > 1
    }
    target_witnesses = {
        target: sorted(actions)
        for target, actions in target_to_actions.items()
        if len(actions) > 1
    }
    witness_count = len(action_witnesses) + len(target_witnesses)

    near_aliases: list[dict[str, object]] = []
    seen_aliases: set[tuple[str, str]] = set()
    for action, target, line in pairs:
        key = (action, target)
        if key in seen_aliases:
            continue
        action_key = semantic_name_key(action)
        target_key = semantic_name_key(target)
        if action_key and action_key == target_key:
            near_aliases.append(
                {
                    "action": action,
                    "target_state": target,
                    "semantic_key": list(action_key),
                    "line": line,
                }
            )
            seen_aliases.add(key)

    typed_independent = bool(
        action_type
        and state_type
        and action_type.strip()
        and state_type.strip()
        and action_type != state_type
    )
    mapping_shape = "none"
    if pairs:
        has_action_fanout = bool(action_witnesses)
        has_target_fanin = bool(target_witnesses)
        if has_action_fanout and has_target_fanin:
            mapping_shape = "many-to-many"
        elif has_action_fanout:
            mapping_shape = "one-action-to-many-states"
        elif has_target_fanin:
            mapping_shape = "many-actions-to-one-state"
        else:
            mapping_shape = "one-to-one"

    diagnostics: list[dict[str, object]] = []
    first_line = pairs[0][2] if pairs else 1
    if action_type and state_type and action_type == state_type:
        diagnostics.append(
            _diagnostic(
                _TYPE_ALIAS_CODE,
                (
                    f"Action projection type `{action_type}` is the same as Target State "
                    "projection type; Action and Target State are not independently typed"
                ),
                first_line,
            )
        )
    for item in near_aliases:
        diagnostics.append(
            _diagnostic(
                _NEAR_ALIAS_CODE,
                (
                    f"Action `{item['action']}` is a lexical near-alias of Target State "
                    f"`{item['target_state']}`; use an operation name for Action and a "
                    "condition name for Target State"
                ),
                int(item["line"]),
            )
        )
    if len(set((action, target) for action, target, _ in pairs)) > 1 and witness_count == 0:
        diagnostics.append(
            _diagnostic(
                _REDUNDANT_AXIS_CODE,
                (
                    "Action and Target State form only a one-to-one mapping; the diagram "
                    "does not contain a behavioral witness that the two axes are independent"
                ),
                first_line,
            )
        )

    analysis = {
        "version": ANALYSIS_VERSION,
        "action_type": action_type,
        "state_type": state_type,
        "typed_independent": typed_independent,
        "mapping_shape": mapping_shape,
        "pair_count": len(set((action, target) for action, target, _ in pairs)),
        "behaviorally_independent": witness_count > 0,
        "behavioral_witness_count": witness_count,
        "action_to_multiple_states": action_witnesses,
        "multiple_actions_to_state": target_witnesses,
        "near_alias_count": len(near_aliases),
        "near_aliases": near_aliases,
    }
    return analysis, diagnostics


__all__ = [
    "ANALYSIS_VERSION",
    "analyze_action_target_independence",
    "semantic_name_key",
]

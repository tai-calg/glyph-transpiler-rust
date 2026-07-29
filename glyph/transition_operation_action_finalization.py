from __future__ import annotations

from copy import deepcopy
from typing import Mapping


ACTION_PROVENANCE = "transition-operation-invocation"
_OUTPUT_COMPATIBILITY_PROVENANCE = "machine-output-projection-compatibility"


def _text(value: object) -> str:
    return str(value or "").strip()


def _replace_output(
    expression: str,
    *,
    original_output: str,
    refined_output: str,
) -> str:
    if not expression or not original_output or not refined_output:
        return expression
    return expression.replace(original_output, refined_output)


def finalize_machine_operation_actions(
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Remove state-output compatibility Actions and restore operation expressions.

    Earlier decision-preimage passes still consume the legacy ``action.variant``
    compatibility field. This final pass runs after enabling-case association and
    guarantees that renderer-visible Action is operation-derived only.
    """

    result = deepcopy(machine_view)
    transitions: list[dict[str, object]] = []
    operation_action_count = 0
    compatibility_removed = 0

    for original in result.get("transitions", []):
        transition = dict(original)
        action = transition.get("action")
        invocations = [
            dict(item)
            for item in transition.get("action_invocations", [])
            if isinstance(item, Mapping)
        ]

        if not invocations:
            if isinstance(action, Mapping):
                compatibility_removed += int(
                    action.get("provenance") == _OUTPUT_COMPATIBILITY_PROVENANCE
                    or bool(action.get("compatibility_only"))
                )
            transition["action"] = None
            transition["action_invocations"] = []
            transitions.append(transition)
            continue

        if not isinstance(action, Mapping):
            transitions.append(transition)
            continue

        value = dict(action)
        decision_variant = _text(value.get("variant"))
        original_output = _text(value.get("output_expression"))
        emitted = transition.get("emitted_output")
        emitted_display = (
            _text(emitted.get("display") or emitted.get("expression"))
            if isinstance(emitted, Mapping)
            else ""
        )
        refined_output = (
            _text(value.get("display") or value.get("expression"))
            if value.get("value_provenance")
            else emitted_display
        )
        template = _text(value.get("operation_template") or value.get("expression"))
        rendered = _replace_output(
            template,
            original_output=original_output,
            refined_output=refined_output,
        )

        value["display"] = rendered
        value["expression"] = rendered
        value["decision_variant"] = decision_variant or None
        value["provenance"] = ACTION_PROVENANCE
        value["compatibility_only"] = False
        value.pop("variant", None)
        value.pop("payload", None)
        transition["action"] = value

        finalized_invocations = []
        for invocation in invocations:
            expression = _replace_output(
                _text(invocation.get("expression")),
                original_output=original_output,
                refined_output=refined_output,
            )
            invocation["expression"] = expression
            finalized_invocations.append(invocation)
        transition["action_invocations"] = finalized_invocations

        finalized_effects = []
        for effect in transition.get("effect_invocations", []):
            if not isinstance(effect, Mapping):
                continue
            item = dict(effect)
            item["expression"] = _replace_output(
                _text(item.get("expression")),
                original_output=original_output,
                refined_output=refined_output,
            )
            finalized_effects.append(item)
        transition["effect_invocations"] = finalized_effects
        operation_action_count += 1
        transitions.append(transition)

    analysis = dict(result.get("analysis", {}))
    analysis["operation_action_finalization_version"] = 1
    analysis["operation_action_transition_count"] = operation_action_count
    analysis["state_output_compatibility_action_count"] = 0
    analysis["removed_output_compatibility_action_count"] = compatibility_removed
    result["transitions"] = transitions
    result["analysis"] = analysis
    return result


__all__ = ["finalize_machine_operation_actions"]

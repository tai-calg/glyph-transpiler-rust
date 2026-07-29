from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from ._transition_action_ir import _OPERATION_ACTION_PROVENANCE, text


_OUTPUT_COMPATIBILITY_PROVENANCE = "machine-output-projection-compatibility"


def _replace_output(
    expression: str,
    *,
    original_output: str,
    refined_output: str,
) -> str:
    if not expression or not original_output or not refined_output:
        return expression
    return expression.replace(original_output, refined_output)


def _remove_legacy_action_segment(
    transition: dict[str, object],
    candidates: list[str],
) -> None:
    label = text(transition.get("display_label"))
    if not label:
        return
    for candidate in sorted({item for item in candidates if item}, key=len, reverse=True):
        label = label.replace(f" / {candidate}", "")
    transition["display_label"] = label


def _refine_emitted_output(
    transition: dict[str, object],
    action: object,
) -> tuple[str, str]:
    emitted = transition.get("emitted_output")
    if not isinstance(emitted, Mapping):
        return "", ""

    output = dict(emitted)
    original_output = text(output.get("display") or output.get("expression"))
    refined_output = original_output
    if isinstance(action, Mapping) and action.get("value_provenance"):
        action_variant = text(action.get("variant"))
        output_variant = text(output.get("variant"))
        if action_variant and action_variant == output_variant:
            refined_output = text(action.get("display") or action.get("expression"))
            output["display"] = refined_output
            output["expression"] = refined_output
            output["payload"] = list(action.get("payload", []))
            output["value_provenance"] = action.get("value_provenance")
            transition["emitted_output"] = output
    return original_output, refined_output


def finalize_machine_operation_actions(
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Remove compatibility-only Actions before renderer-visible publication."""

    result = deepcopy(machine_view)
    transitions: list[dict[str, object]] = []
    operation_action_count = 0
    compatibility_removed = 0

    for original in result.get("transitions", []):
        transition = dict(original)
        action = transition.get("action")
        prefinal_action = (
            text(action.get("display") or action.get("expression"))
            if isinstance(action, Mapping)
            else ""
        )
        operation_template = (
            text(action.get("operation_template"))
            if isinstance(action, Mapping)
            else ""
        )
        original_output, refined_output = _refine_emitted_output(transition, action)
        invocations = [
            dict(item)
            for item in transition.get("action_invocations", [])
            if isinstance(item, Mapping)
        ]

        if not invocations:
            _remove_legacy_action_segment(
                transition,
                [prefinal_action, original_output, refined_output],
            )
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
        decision_variant = text(value.get("variant"))
        compatibility_output = text(value.get("output_expression"))
        if compatibility_output:
            original_output = compatibility_output
        emitted = transition.get("emitted_output")
        emitted_display = (
            text(emitted.get("display") or emitted.get("expression"))
            if isinstance(emitted, Mapping)
            else ""
        )
        if not refined_output:
            refined_output = emitted_display
        template = text(value.get("operation_template") or value.get("expression"))
        rendered = _replace_output(
            template,
            original_output=original_output,
            refined_output=refined_output,
        )

        _remove_legacy_action_segment(
            transition,
            [prefinal_action, operation_template, template, rendered],
        )
        value["display"] = rendered
        value["expression"] = rendered
        value["decision_variant"] = decision_variant or None
        value["provenance"] = _OPERATION_ACTION_PROVENANCE
        value["compatibility_only"] = False
        value.pop("variant", None)
        value.pop("payload", None)
        transition["action"] = value

        finalized_invocations = []
        for invocation in invocations:
            invocation["expression"] = _replace_output(
                text(invocation.get("expression")),
                original_output=original_output,
                refined_output=refined_output,
            )
            finalized_invocations.append(invocation)
        transition["action_invocations"] = finalized_invocations

        finalized_effects = []
        for effect in transition.get("effect_invocations", []):
            if not isinstance(effect, Mapping):
                continue
            item = dict(effect)
            item["expression"] = _replace_output(
                text(item.get("expression")),
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

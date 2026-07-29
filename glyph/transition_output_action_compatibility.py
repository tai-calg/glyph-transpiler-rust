from __future__ import annotations

from copy import deepcopy
from typing import Mapping


_COMPATIBILITY_PROVENANCE = "machine-output-projection-compatibility"


def attach_output_action_compatibility(
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Temporarily expose emitted-output variants to legacy decision passes.

    Input-preimage and enabling-case association historically read
    ``transition.action.variant``. Until those readers migrate, this pass adds a
    compatibility variant. A later finalization pass removes all compatibility
    values before renderer-visible IR is published.
    """

    result = deepcopy(machine_view)
    transitions: list[dict[str, object]] = []
    compatibility_count = 0

    for original in result.get("transitions", []):
        transition = dict(original)
        emitted = transition.get("emitted_output")
        if not isinstance(emitted, Mapping):
            transitions.append(transition)
            continue

        variant = str(emitted.get("variant") or "").strip()
        if not variant:
            transitions.append(transition)
            continue

        action = transition.get("action")
        if isinstance(action, Mapping):
            value = dict(action)
            value["variant"] = variant
            value["payload"] = list(emitted.get("payload", []))
            value["decision_variant"] = variant
            value["output_expression"] = str(
                emitted.get("expression") or emitted.get("display") or ""
            )
            value["operation_template"] = str(
                action.get("expression") or action.get("display") or ""
            )
            value["compatibility_only"] = False
            transition["action"] = value
        else:
            value = dict(emitted)
            value["provenance"] = _COMPATIBILITY_PROVENANCE
            value["compatibility_only"] = True
            transition["action"] = value
            compatibility_count += 1
        transitions.append(transition)

    analysis = dict(result.get("analysis", {}))
    analysis["output_action_compatibility_version"] = 1
    analysis["output_action_compatibility_count"] = compatibility_count
    result["transitions"] = transitions
    result["analysis"] = analysis
    return result


__all__ = ["attach_output_action_compatibility"]

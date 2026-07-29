from __future__ import annotations

from copy import deepcopy
from typing import Mapping



def preserve_legacy_transition_metadata(
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Keep v4 trigger metadata while v1 enabling_cases are the semantic source."""

    result = deepcopy(machine_view)
    transitions: list[dict[str, object]] = []
    for original in result.get("transitions", []):
        transition = dict(original)
        cases = transition.get("enabling_cases")
        if not isinstance(cases, list) or not cases:
            transitions.append(transition)
            continue
        first = cases[0]
        input_pattern = first.get("input_pattern") if isinstance(first, Mapping) else None
        preimage = transition.get("input_preimage")
        if isinstance(input_pattern, Mapping):
            trigger = dict(transition.get("trigger") or {})
            trigger.update(
                {
                    "display": input_pattern.get("display"),
                    "expression": input_pattern.get("expression"),
                    "role": "inferred-trigger",
                    "confidence": "dataflow-expanded",
                    "provenance": "decision-output-preimage",
                    "provenance_roots": list(
                        input_pattern.get("provenance_roots", [])
                    ),
                }
            )
            if isinstance(preimage, Mapping):
                trigger["decision_function"] = preimage.get("decision_function")
                trigger["decision_variant"] = preimage.get("decision_variant")
            transition["trigger"] = trigger
            transition["event"] = str(input_pattern.get("display") or "")
        transitions.append(transition)
    result["transitions"] = transitions
    return result


__all__ = ["preserve_legacy_transition_metadata"]

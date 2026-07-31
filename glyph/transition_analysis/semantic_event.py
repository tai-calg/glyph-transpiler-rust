from __future__ import annotations

from copy import deepcopy
from typing import Mapping, Sequence

from .witness_binding import canonical_digest


SEMANTIC_EVENT_IDENTITY_VERSION = 1


def attach_context_semantic_event_refs(
    context: dict[str, object],
    *,
    program_fingerprint: str,
    edge_fingerprint: str | None,
) -> None:
    """Attach ordered semantic identities to native EffectTrace events.

    ``static_event_id`` identifies the normalized event shape. ``trace_position``
    identifies the dynamic occurrence in the exact trace, so two equal calls remain
    two distinct events. No reference is emitted when the relation edge identity is
    unavailable; the Exact checker will then reject the native context.
    """

    if not edge_fingerprint:
        return
    effect_trace = _mapping(context.get("effect_trace"))
    alternatives = effect_trace.get("alternatives")
    if not _sequence(alternatives):
        return
    for alternative_index, alternative in enumerate(alternatives):
        if not isinstance(alternative, dict):
            continue
        events = alternative.get("events")
        if not _sequence(events):
            continue
        for trace_position, event in enumerate(events):
            if not isinstance(event, dict):
                continue
            static_event_id = canonical_digest(
                {
                    "version": SEMANTIC_EVENT_IDENTITY_VERSION,
                    "operation": event.get("operation"),
                    "expression": event.get("expression"),
                    "failure_type": event.get("failure_type"),
                }
            )
            reference = {
                "version": SEMANTIC_EVENT_IDENTITY_VERSION,
                "program_fingerprint": program_fingerprint,
                "analysis_edge_fingerprint": edge_fingerprint,
                "system": context.get("system"),
                "entry": context.get("entry"),
                "alternative_index": alternative_index,
                "static_event_id": static_event_id,
                "trace_position": trace_position,
            }
            reference["id"] = canonical_digest(reference)
            event["semantic_event_ref"] = reference


def attach_machine_action_aliases(
    transition: Mapping[str, object],
    system_action: Mapping[str, object] | None,
) -> dict[str, object]:
    """Mark a Machine projection as an alias only with event-by-event identity.

    The EffectTrace is never changed. Equal display strings alone are insufficient.
    The complete Machine invocation sequence must match the exact System EffectTrace
    sequence in operation, expression and failure type. Repeated identical calls are
    preserved because each system event has a distinct ``trace_position`` and id.
    """

    result = deepcopy(dict(transition))
    if not isinstance(system_action, Mapping) or system_action.get("kind") != "effect-trace":
        return result
    system_events = _mappings(system_action.get("events"))
    machine_invocations = _mappings(result.get("machine_action_invocations"))
    if not system_events or len(machine_invocations) != len(system_events):
        return result
    if any(
        _event_shape(machine) != _event_shape(system)
        for machine, system in zip(machine_invocations, system_events, strict=True)
    ):
        return result
    references = tuple(
        _mapping(event.get("semantic_event_ref")) for event in system_events
    )
    if any(not reference.get("id") for reference in references):
        return result
    reference_ids = [str(reference["id"]) for reference in references]

    result["machine_action_invocations"] = _alias_invocations(
        machine_invocations,
        references,
    )
    machine_effects = _mappings(result.get("machine_effect_invocations"))
    if len(machine_effects) == len(references) and all(
        _event_shape(machine) == _event_shape(system)
        for machine, system in zip(machine_effects, system_events, strict=True)
    ):
        result["machine_effect_invocations"] = _alias_invocations(
            machine_effects,
            references,
        )

    machine_action = result.get("machine_action")
    if isinstance(machine_action, Mapping):
        updated_action = deepcopy(dict(machine_action))
        updated_action["projection_role"] = "compatibility-alias"
        updated_action["semantic_event_refs"] = [dict(item) for item in references]
        updated_action["alias_of_event_ids"] = reference_ids
        result["machine_action"] = updated_action

    result["semantic_action_aliasing"] = {
        "version": SEMANTIC_EVENT_IDENTITY_VERSION,
        "status": "proven-alias",
        "event_ids": reference_ids,
        "event_count": len(reference_ids),
    }
    return result


def action_event_reference_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ()
    if value.get("kind") == "effect-trace":
        return tuple(
            str(reference.get("id"))
            for event in _mappings(value.get("events"))
            for reference in (_mapping(event.get("semantic_event_ref")),)
            if reference.get("id")
        )
    return tuple(
        str(reference.get("id"))
        for reference in _mappings(value.get("semantic_event_refs"))
        if reference.get("id")
    )


def actions_are_same_semantic_events(
    machine_action: object,
    system_action: object,
) -> bool:
    machine_ids = action_event_reference_ids(machine_action)
    system_ids = action_event_reference_ids(system_action)
    return bool(machine_ids) and machine_ids == system_ids


def _alias_invocations(
    invocations: Sequence[Mapping[str, object]],
    references: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for invocation, reference in zip(invocations, references, strict=True):
        item = deepcopy(dict(invocation))
        item["projection_role"] = "compatibility-alias"
        item["semantic_event_ref"] = dict(reference)
        item["alias_of_event_id"] = reference["id"]
        result.append(item)
    return result


def _event_shape(event: Mapping[str, object]) -> tuple[object, ...]:
    return (
        _text(event.get("operation")),
        _text(event.get("expression")),
        _text(event.get("failure_type")),
    )


def _text(value: object) -> str:
    return str(value or "").strip()


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _mappings(value: object) -> tuple[Mapping[str, object], ...]:
    if not _sequence(value):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


__all__ = [
    "SEMANTIC_EVENT_IDENTITY_VERSION",
    "action_event_reference_ids",
    "actions_are_same_semantic_events",
    "attach_context_semantic_event_refs",
    "attach_machine_action_aliases",
]

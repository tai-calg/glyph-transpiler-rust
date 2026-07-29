from __future__ import annotations

from typing import Mapping, Sequence


_OPERATION_ACTION_PROVENANCE = "transition-operation-invocation"
_RESULT_CONSUMER_PROVENANCE = "transition-result-consumer"
_DECLARED_EFFECT_PROVENANCE = "declared-effect-invocation"
_OUTPUT_PROJECTION_PROVENANCE = "machine-output-projection"


def text(value: object) -> str:
    return str(value or "").strip()


def invocation_key(
    invocation: Mapping[str, object],
) -> tuple[str, object]:
    return text(invocation.get("expression")), invocation.get("failure_type")


def renumber_invocations(
    invocations: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    result = [dict(item) for item in invocations]
    for sequence, invocation in enumerate(result, start=1):
        invocation["sequence"] = sequence
    return result


def merge_unique_invocations(
    existing: Sequence[Mapping[str, object]],
    additions: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    result = [dict(item) for item in existing]
    seen = {invocation_key(item) for item in result}
    for addition in additions:
        key = invocation_key(addition)
        if key in seen:
            continue
        result.append(dict(addition))
        seen.add(key)
    return renumber_invocations(result)


def build_operation_action(
    invocations: Sequence[Mapping[str, object]],
    *,
    source: Mapping[str, object] | None = None,
) -> dict[str, object] | None:
    expressions = [text(item.get("expression")) for item in invocations]
    expressions = [item for item in expressions if item]
    if not expressions:
        return None
    operations = [text(item.get("operation")) for item in invocations]
    operations = [item for item in operations if item]
    display = "; ".join(expressions)
    action_source: object = source
    if action_source is None and invocations:
        action_source = invocations[0].get("source")
    if action_source is None:
        action_source = {"line": 1, "column": 1}
    return {
        "display": display,
        "expression": display,
        "operation": operations[0] if len(operations) == 1 else None,
        "operations": operations,
        "kind": (
            "operation-invocation"
            if len(expressions) == 1
            else "operation-sequence"
        ),
        "effectful": True,
        "provenance": _OPERATION_ACTION_PROVENANCE,
        "source": (
            dict(action_source)
            if isinstance(action_source, Mapping)
            else action_source
        ),
    }

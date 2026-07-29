# Transition Operation Action Semantics v2

Status: Implemented

## Purpose

An Action is an operation invocation proven to execute. It is not a Target State, an Emitted Output, a state-field value, or a lexical alias of any of those values.

No Glyph syntax is added by this contract.

Action ownership is defined by `state-transition-action-scopes-v1.md`.

## Semantic axes

### Target State

Selected only through `machine select=` and represented by the destination node.

### Emitted Output

A value projected from the transition result by the legacy source spelling `machine action=state.field`. The public semantic field is `emitted_output`; the value is not an Action.

### Machine Action

Operations proven to execute inside the machine transition expression.

IR fields:

```text
machine_action
machine_action_invocations
machine_effect_invocations
```

### System execution Action

Operations executed by a concrete `system entry` after consuming the machine transition result.

IR field:

```text
execution_action_bindings[]
```

A System Action never mutates `machine_action`.

### Display Action

The operation sequence selected for the current diagram projection.

IR fields:

```text
display_action
display_action_invocations
display_effect_invocations
```

Compatibility fields `action`, `action_invocations`, and `effect_invocations` mirror the display projection for existing public StateTransitionIR v4 readers.

## Invariants

1. Target State is obtained only from the state selector.
2. Emitted Output is obtained only from the output projection.
3. Every Action has a structured operation-invocation witness.
4. Target State is never an Action fallback.
5. Emitted Output is never an Action fallback.
6. An intrinsic transition with no operation has `machine_action = null`.
7. A caller operation belongs to its System execution binding, not to the reusable Machine Action.
8. Divergent system contexts are retained separately and require context selection.
9. Machine operations precede downstream system operations in a composed display sequence.
10. A failed machine operation does not produce a transition result for downstream system consumption.
11. Renderer code consumes structured IR and performs no name-based Action inference.
12. Input Pattern, Guard, Action, Emitted Output, Effect, and Target State remain separate roles.

## Examples

Intrinsic Machine Action:

```json
{
  "target_state": "Stopped",
  "emitted_output": {
    "display": "EmergencyBrake",
    "provenance": "machine-output-projection"
  },
  "machine_action": {
    "display": "write_motor(EmergencyBrake)",
    "provenance": "transition-operation-invocation",
    "scope": "machine"
  },
  "execution_action_bindings": []
}
```

System result-consumer Action:

```json
{
  "target_state": "Opening",
  "machine_action": null,
  "execution_action_bindings": [
    {
      "system": "DoorControl",
      "entry": "control",
      "action": {
        "display": "actuator(DoorState(Opening))"
      }
    }
  ],
  "display_action": {
    "display": "actuator(DoorState(Opening))",
    "provenance": "transition-operation-invocation",
    "projection_provenance": "transition-display-action-projection",
    "scope": "system"
  }
}
```

Divergent systems:

```text
DoorControl/control → actuator(DoorState(Opening))
DoorAudit/audit_control → audit(DoorState(Opening))
```

Both bindings remain in IR. `display_action` is not guessed until an execution context is selected.

## Rendering contract

```text
Input Pattern [Guard] ➞ Display Action
```

Examples:

```text
input.emergency [!input.fault] ➞ write_motor(EmergencyBrake)
? input.open_request&input.authorized ➞ actuator(DoorState(Opening))
[otherwise] ➞ actuator(DoorState(Closed))
```

Invalid:

```text
input.emergency ➞ Stopped
input.emergency ➞ EmergencyBrake
[otherwise] ➞ actuator(state)
```

## Compatibility and versions

- `machine action=state.field` remains parse-compatible and maps to `emitted_output`.
- Public StateTransitionIR remains v4 because the scope fields are additive and compatibility Action fields remain available.
- `transition_operation_action_version = 2` identifies operation-derived Actions.
- `transition_result_consumer_action_version = 2` identifies broad caller analysis and per-system bindings.
- `transition_action_scope_version = 1` identifies explicit Machine/System/Display separation.

## Verification

Required regressions cover:

- branch-local external operations;
- direct, bound, aliased, nested, and pure-wrapper transition-result consumers;
- unrelated operations remaining non-Actions;
- divergent system bindings;
- multiple machine calls being diagnosed rather than collapsed;
- Target State and Emitted Output separation;
- exact default-workspace concrete actuator values;
- compiler, browser, SVG, PNG, PDF, layout, and snapshot suites.

# Transition Operation Action Semantics v2

Status: Implemented

## Purpose

This specification corrects the semantic source of the `Action` rendered on a state-transition edge.

The previous implementation projected `machine action=state.field` from the next state value and rendered that state-carried value as Action. Renaming the projected variants does not fix the category error: a field transported inside a state value is not proof that an operation was executed.

No new Glyph syntax is introduced in this change.

## Terms

### Target State

The state value selected only by `machine select=` from the transition result. It is rendered by the destination node and never copied into an edge Action.

### Emitted Output

A data value projected from the transition result by the legacy `machine action=state.field` selector. It may be a command, token, request, receipt selector, or other value transported for later interpretation.

Despite the legacy source spelling, an Emitted Output is not an Action. IR field: `emitted_output`.

### Operation Invocation

A call expression in the transition branch whose callee is recognized by the compiler as an executable declared operation.

### Action

One or more Operation Invocations actually performed by the transition branch. Action is an execution occurrence, not a state value, state name, target name, command variant, or inferred synonym.

### Effect

The side-effect property and failure semantics of an Operation Invocation. An effectful invocation can simultaneously be an Action occurrence and an Effect occurrence; the two terms describe different axes.

### Action Sequence

An ordered list of Operation Invocations executed by one transition branch. IR field: `action_invocations`.

## Invariants

1. `target_state` is obtained only from the state selector.
2. `emitted_output` is obtained only from the legacy state-field projection.
3. `action` and `action_invocations` are obtained only from proven Operation Invocations.
4. Target State is never used as an Action fallback.
5. Emitted Output is never used as an Action fallback.
6. A transition with no proven Operation Invocation has `action = null`.
7. Renderer code consumes structured Action IR and does not infer an Action from names.
8. Input Pattern, Guard, Action, Emitted Output, Effect, and Target State remain separate semantic roles.
9. Decision-preimage analysis may use Emitted Output to associate a decision result with a transition, but the renderer must not display that value as Action.
10. Existing source using `machine action=` remains parse-compatible while its IR role is reclassified.

## IR contract

A transition with one executed operation:

```json
{
  "target_state": "Stopped",
  "emitted_output": {
    "display": "EmergencyBrake",
    "variant": "EmergencyBrake",
    "provenance": "machine-output-projection"
  },
  "action_invocations": [
    {
      "operation": "write_motor",
      "expression": "write_motor(EmergencyBrake)",
      "effectful": true,
      "sequence": 1,
      "provenance": "declared-effect-invocation"
    }
  ],
  "action": {
    "display": "write_motor(EmergencyBrake)",
    "expression": "write_motor(EmergencyBrake)",
    "kind": "operation-invocation",
    "effectful": true,
    "provenance": "transition-operation-invocation"
  }
}
```

A transition that only emits a command and performs no operation:

```json
{
  "emitted_output": {
    "display": "Unlock"
  },
  "action_invocations": [],
  "action": null
}
```

## Rendering contract

The state-transition label remains:

```text
Input Pattern [Guard] ➞ Action
```

The arrow destination represents Target State. Emitted Output is not rendered in the Action position.

Examples:

```text
input.emergency [!input.fault] ➞ write_motor(EmergencyBrake)
[otherwise] ➞ write_motor(SetMotorPower(normalize(input.raw)))
```

Invalid renderings:

```text
input.emergency ➞ Stopped
input.emergency ➞ EmergencyBrake
```

The first substitutes Target State. The second substitutes a transported command value without proving that an operation was invoked.

## Compatibility

- `machine action=state.field` remains accepted in source.
- Existing machine metadata `action_projection` remains available but is marked as the legacy source spelling for `output_projection`.
- Transition IR adds `emitted_output` and `action_invocations`.
- Legacy consumers may continue reading `action`, but its provenance changes to operation invocation only.
- Decision-preimage and enabling-case passes use `emitted_output.variant` before any legacy fallback.

## Verification

Required tests:

1. A state-field projection produces `emitted_output`, never `action`.
2. A proven operation call produces `action` and `action_invocations`.
3. A transition with no operation has no Action.
4. Target State never appears through Action fallback.
5. Enabling-case association continues through `emitted_output.variant`.
6. DOM Action text equals the operation expression.
7. DOM Action text differs from both Target State and Emitted Output.
8. README Motor Safety labels render `write_motor(...)` operations.
9. Existing Input Pattern and Guard separation remains unchanged.
10. Compiler, browser, desktop, and snapshot regression suites pass.

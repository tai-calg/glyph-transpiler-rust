# Transition Operation Action Semantics v2

Status: Implemented

Verification status: compiler IR, DOM rendering, SVG/PNG/PDF export, README snapshot, target-state independence, and transition-result consumer regressions pass with operation-derived Actions.

Snapshot basis: the committed README image is generated and compared in the pull-request merge context, so it verifies the semantics that will exist on `main` after merge.

## Purpose

This specification corrects the semantic source of the `Action` rendered on a state-transition edge.

The previous implementation projected `machine action=state.field` from the next state value and rendered that state-carried value as Action. Renaming the projected variants does not fix the category error: a field transported inside a state value is not proof that an operation was executed.

No new Glyph syntax is introduced in this change.

Downstream attribution through a caller Result Binding is specified by `transition-result-consumer-action-dataflow-v1.md`.

## Terms

### Target State

The state value selected only by `machine select=` from the transition result. It is rendered by the destination node and never copied into an edge Action.

### Emitted Output

A data value projected from the transition result by the legacy `machine action=state.field` selector. It may be a command, token, request, receipt selector, or other value transported for later interpretation.

Despite the legacy source spelling, an Emitted Output is not an Action. IR field: `emitted_output`.

### Operation Invocation

A call expression whose callee is recognized by the compiler as an executable declared operation.

### Action

One or more Operation Invocations proven to execute as part of the transition path. An invocation may occur directly in the transition branch or downstream when the caller consumes that branch's complete result. Action is an execution occurrence, not a state value, state name, target name, command variant, or inferred synonym.

### Effect

The side-effect property and failure semantics of an Operation Invocation. An effectful invocation can simultaneously be an Action occurrence and an Effect occurrence; the two terms describe different axes.

### Action Sequence

An ordered list of Operation Invocations executed by one transition path. Branch-local operations precede downstream result-consumer operations. IR field: `action_invocations`.

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
11. A downstream operation is attributable only when immutable dataflow proves that it consumes the complete Transition Result.
12. Ambiguous or unresolved caller paths never create a guessed Action.

## IR contract

A transition with one branch-local operation:

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

A transition whose result is consumed by its caller:

```json
{
  "target_state": "Opening",
  "action_invocations": [
    {
      "operation": "actuator",
      "expression": "actuator(DoorState(Opening))",
      "sequence": 1,
      "provenance": "transition-result-consumer"
    }
  ],
  "action": {
    "display": "actuator(DoorState(Opening))",
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
? input.open_request&input.authorized ➞ actuator(DoorState(Opening))
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
- `transition_result_consumer_action_version = 1` identifies downstream caller attribution.

## Verification

Required tests:

1. A state-field projection produces `emitted_output`, never `action`.
2. A proven branch-local operation produces `action` and `action_invocations`.
3. `step → next → actuator(next)` produces a branch-specialized operation Action.
4. Immutable aliases preserve Transition Result provenance.
5. A pure guarded helper selects only the operation proven for the concrete Transition Result.
6. An unrelated operation after `step` is not attributed.
7. Divergent caller contexts produce a diagnostic and no guessed Action.
8. A transition with no operation has no Action.
9. Target State never appears through Action fallback.
10. Enabling-case association continues through `emitted_output.variant`.
11. DOM Action text equals the operation expression.
12. DOM Action text differs from both Target State and Emitted Output.
13. The exact default workspace source renders `actuator(DoorState(...))` Actions.
14. README Motor Safety labels render `write_motor(...)` operations.
15. Compiler, browser, desktop, export, and snapshot regression suites pass.

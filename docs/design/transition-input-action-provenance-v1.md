# Transition Input → Action Provenance v1

Status: Implemented; Action-source definition corrected by `transition-operation-action-semantics-v2.md`

## Problem

A transition label must not use an intermediate discriminator as its Input merely because a downstream state function branches on that value. It must also not present a state value, command value, or Target State as though that value were an executed Action.

For:

```glyph
command := decide(input)
command == EmergencyBrake >>
  MotorState(Stopped, EmergencyBrake, write_motor(EmergencyBrake))
```

and:

```glyph
>decide(input:Input):MotorCommand
  input.fault >> LatchFault
  input.emergency >> EmergencyBrake
  !input.enabled >> DisableMotor
  _ >> SetMotorPower(normalize(input.raw))
```

the semantic roles are:

```text
Input          = authored input pattern obtained from decide(input) preimage
Guard          = authored or generated additional applicability condition
Emitted Output = command value projected by legacy machine action=
Action         = operation invocation executed by the transition branch
Target State   = state value projected by machine select=
Effect         = side-effect and failure metadata of an operation invocation
```

`EmergencyBrake` is an Emitted Output. `write_motor(EmergencyBrake)` is the Action. `Stopped` is the Target State. These values must not be substituted for one another.

## Invariants

- Input is derived only from machine input parameters or declared external input roots.
- Guard is retained separately from Input through `enabling_cases`.
- Emitted Output is derived from the legacy `machine action=state.field` projection.
- Action is derived only from proven operation invocations in the transition branch.
- An effectful operation invocation may be both an Action occurrence and an Effect occurrence; these are different semantic axes.
- Target State is derived only from `machine select=state.field`.
- Target State never populates Action.
- Emitted Output never populates Action.
- A transition with no operation invocation has `action = null`.
- Failed Input-preimage expansion preserves the existing provisional trigger and emits `STIR_INPUT_PREIMAGE_UNRESOLVED`.
- Renderers consume structured Input, Guard, and Action IR; they do not infer roles from strings or names.

## Compiler passes

```text
compile transitions
  → project Target State
  → project legacy state-field value as Emitted Output
  → discover executed operation invocations
  → classify local conditions
  → expand decision-result preimages
  → build Input/Guard enabling cases
  → finalize operation-derived Action
  → analyze Action/Target independence
  → render
```

A compatibility bridge may temporarily expose `emitted_output.variant` to older decision-preimage passes. The final published IR removes that compatibility value from `action` before rendering.

## Input-preimage IR

The trigger object records dataflow provenance:

```json
{
  "display": "input.emergency&!input.fault",
  "expression": "input.emergency&!input.fault",
  "role": "inferred-trigger",
  "confidence": "dataflow-expanded",
  "provenance": "decision-output-preimage",
  "decision_function": "decide",
  "decision_variant": "EmergencyBrake",
  "provenance_roots": ["input:input"]
}
```

`enabling_cases` then separates the authored Input Pattern from generated priority Guard:

```json
{
  "input_pattern": {
    "expression": "input.emergency"
  },
  "guard": {
    "expression": "!input.fault",
    "terms": [
      {"origin": "priority-exclusion"}
    ]
  },
  "enabling_condition": {
    "expression": "input.emergency&!input.fault"
  }
}
```

## Output and Action IR

```json
{
  "emitted_output": {
    "display": "EmergencyBrake",
    "variant": "EmergencyBrake",
    "provenance": "machine-output-projection"
  },
  "action_invocations": [
    {
      "operation": "write_motor",
      "expression": "write_motor(EmergencyBrake)",
      "provenance": "declared-effect-invocation"
    }
  ],
  "action": {
    "display": "write_motor(EmergencyBrake)",
    "kind": "operation-invocation",
    "provenance": "transition-operation-invocation"
  },
  "target_state": "Stopped"
}
```

## Action/Target independence

The independence analysis receives operation Actions after compatibility finalization. For Motor Safety, one operation family reaches multiple states:

```json
{
  "action_type": "OperationInvocation",
  "state_type": "Mode",
  "typed_independent": true,
  "mapping_shape": "one-action-to-many-states",
  "action_to_multiple_states": {
    "write_motor": ["Faulted", "Running", "Stopped"]
  }
}
```

This is structural evidence that Action and Target State are independent axes. The analysis does not use state names or emitted command variants as Action substitutes.

## Conservative boundaries

Input-preimage expansion performs no arbitrary symbolic execution, recursion expansion, Effect execution, or target-based inference.

Action discovery accepts only operation invocations recognized by compiler structure. It does not infer an Action from:

- Target State names;
- Emitted Output variants;
- state-field names;
- lexical similarity;
- business-domain assumptions.

## README publishing gate

Before a state screenshot can replace the README image, compiler and snapshot verification must prove:

- `transition_operation_action_version = 2`;
- every rendered Action has `provenance=transition-operation-invocation`;
- every rendered Action has at least one structured operation-invocation witness;
- no Action equals Target State;
- no Action equals Emitted Output;
- Input and Guard are separated through `enabling_cases`;
- the visible label contains `Input [Guard] ➞ Action`;
- the generated PNG matches the committed README PNG within bounded rasterization tolerance.

No domain-specific Action or state name is hardcoded in this gate. Compiler IR and DOM contracts are primary evidence; the screenshot is secondary evidence.

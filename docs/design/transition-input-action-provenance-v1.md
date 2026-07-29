# Transition Input → Action Provenance v1

Status: Implemented

## Problem

A transition label must not use an intermediate discriminator as its Input merely because a downstream state function branches on that value. It must also not present Action as a renamed copy of Target State.

For:

```glyph
command := decide(input)
command == EmergencyBrake >> MotorState(Stopped,EmergencyBrake)
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
Input   = preimage conditions in decide(input)
Action  = operation value projected by machine action=
Target  = state value projected by machine select=
Effect  = effect_invocations
```

`EmergencyBrake` and `DisableMotor` are different Actions that can both lead to `Stopped`. This is a behavioral witness that Action and Target State are independent axes, rather than two labels for the same transition result.

## Invariants

- Input is derived only from machine input parameters or declared external input roots.
- Action is derived only from `machine action=state.field`.
- Target State is derived only from `machine select=state.field`.
- Effect invocations never populate Action.
- Target State never populates Action.
- Action projection type and Target State projection type are analyzed independently.
- A shared projection type emits `STIR_ACTION_TARGET_TYPE_ALIAS`.
- Lexical near-aliases such as `Stop` / `Stopped`, `RunAction` / `RunningState`, and `OpenValveCommand` / `ValveOpenedMode` emit `STIR_ACTION_TARGET_NEAR_ALIAS`.
- A purely one-to-one Action↔Target mapping emits `STIR_ACTION_TARGET_REDUNDANT_AXIS` because the compiled machine contains no behavioral independence witness.
- A behavioral witness exists when one Action reaches multiple Target States or multiple Actions reach one Target State.
- Failed Input-preimage expansion preserves the existing provisional trigger and emits `STIR_INPUT_PREIMAGE_UNRESOLVED`.
- Renderers consume structured Input and Action; they do not infer either role.

The compiler diagnostics remain warnings for compatibility. Publication gates may require stronger conditions.

## Compiler passes

```text
compile transitions
  → project Action
  → classify local conditions
  → expand discriminator preimages
  → analyze Action/Target independence
  → render
```

The independence pass is generic. It does not contain Motor, Door, Stop, Stopped, or other example-specific allowlists.

## Input-preimage IR

The trigger object records dataflow provenance without changing Action or Effect fields:

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

`analysis.input_preimage_version` is `1`.

## Action/Target independence IR

Every compiled machine exposes:

```json
{
  "analysis": {
    "action_target_independence": {
      "version": 1,
      "action_type": "MotorCommand",
      "state_type": "Mode",
      "typed_independent": true,
      "mapping_shape": "many-actions-to-one-state",
      "behaviorally_independent": true,
      "behavioral_witness_count": 1,
      "multiple_actions_to_state": {
        "Stopped": ["DisableMotor", "EmergencyBrake"]
      },
      "action_to_multiple_states": {},
      "near_alias_count": 0,
      "near_aliases": []
    }
  }
}
```

The mapping analysis uses structured Action variants and Target State values. Payload expressions such as `SetMotorPower(normalize(input.raw))` are grouped by the Action variant `SetMotorPower`.

## Lexical near-alias analysis

Identifiers are split across CamelCase, snake_case, and punctuation. Generic role words such as `Action`, `Command`, `State`, `Mode`, and `Status` are removed. Conservative inflection normalization then compares the remaining semantic tokens.

Examples detected without a domain-specific dictionary:

```text
Stop                  ≈ Stopped
RunAction             ≈ RunningState
OpenValveCommand      ≈ ValveOpenedMode
```

This diagnostic is evidence of naming ambiguity, not a claim that arbitrary natural-language semantics can be fully inferred by the compiler.

## Conservative boundaries

Input-preimage expansion performs no arbitrary symbolic execution, recursion expansion, Effect execution, or target-based inference.

Action/Target independence analysis deliberately does not:

- infer business meaning from unrelated words;
- reject a machine solely because it has one transition;
- treat synthesized failure transitions as independence witnesses;
- require all valid machines to have a many-to-many mapping.

It reports structural evidence. The README publication gate requires stronger evidence because the image is intended to teach the distinction.

## Verification

### Generic semantic tests

- distinct Action and Target State types are recognized;
- same-type projections emit `STIR_ACTION_TARGET_TYPE_ALIAS`;
- lexical near-aliases emit `STIR_ACTION_TARGET_NEAR_ALIAS` across arbitrary domain names;
- a one-to-one mapping emits `STIR_ACTION_TARGET_REDUNDANT_AXIS`;
- many Actions reaching one state prove behavioral independence;
- synthesized failure transitions do not fabricate independence;
- renaming Input, Action, or Target changes only its own axis.

### README publishing gate

Before a state screenshot can replace the README image, compiler and snapshot verification must prove:

- the Action and Target State projection types are distinct;
- the compiled mapping contains at least one behavioral independence witness;
- the mapping is not purely one-to-one;
- no Action is a lexical near-alias of its Target State;
- the visible label contains `Input [Guard] ➞ Action`;
- the generated PNG matches the committed README PNG within bounded rasterization tolerance.

No Action or state name is hardcoded in this gate. The screenshot remains secondary evidence; compiler IR and DOM contract tests are primary evidence.

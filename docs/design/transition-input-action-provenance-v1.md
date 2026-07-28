# Transition Input → Action Provenance v1

Status: Implemented

## Problem

A transition label must not use an intermediate discriminator such as `DisableMotor` or `SetMotorPower` as its Input merely because a downstream state function branches on `command == DisableMotor`.

For:

```glyph
command := decide(input)
command == DisableMotor >> MotorState(Stopped,DisableMotor)
```

and:

```glyph
>decide(input:Input):MotorCommand
  input.emergency|input.fault >> DisableMotor
  !input.enabled >> DisableMotor
  _ >> SetMotorPower(normalize(input.raw))
```

the semantic roles are:

```text
Input   = preimage conditions in decide(input)
Action  = projection declared by machine action=
Target  = projection declared by machine select=
Effect  = effect_invocations
```

`DisableMotor` is an Action value, not an Input event or a state name. `Stopped` is the Target State reached after that command is selected.

## Invariants

- Input is derived only from machine input parameters or declared external input roots.
- Action is derived only from `machine action=state.field`.
- Target State is derived only from `machine select=state.field`.
- Effect invocations never populate Action.
- Target State never populates Action.
- An intermediate sum variant may appear as Action, but may not be published as Input when its defining call can be expanded.
- Failed expansion preserves the existing provisional trigger and emits `STIR_INPUT_PREIMAGE_UNRESOLVED`.
- Renderers consume structured Input and Action; they do not infer either role.
- The README publication example uses command names for Action and state names for Target State; lexical near-aliases such as `Stop` / `Stopped` are forbidden in that example.

## Compiler pass

A new pass runs after Action projection and initial trigger/guard classification.

```text
compile transitions
  → project Action
  → classify local conditions
  → expand discriminator preimages
  → render
```

For a transition discriminator:

```text
local == Variant(pattern_bindings)
```

the pass resolves:

```text
local := decision(machine_inputs)
```

then inspects the guarded clauses of `decision`. Clauses whose result has the same sum variant form the Input preimage.

Ordered guards are preserved. A matching clause is excluded by earlier clauses only when those earlier clauses produce a different result variant. A fallback clause is rendered as `otherwise` while its exact predicate is retained in IR metadata.

Parameter substitution maps decision-function parameters to call arguments. Pattern payloads may refine a symbolic Action such as `SetMotorPower(power)` to `SetMotorPower(normalize(input.raw))` when the mapping is unique.

## IR extension

The existing trigger object gains provenance fields without changing Action or Effect fields:

```json
{
  "display": "input.emergency|input.fault|!input.enabled",
  "expression": "input.emergency|input.fault|!input.enabled",
  "role": "inferred-trigger",
  "confidence": "dataflow-expanded",
  "provenance": "decision-output-preimage",
  "decision_function": "decide",
  "decision_variant": "DisableMotor",
  "provenance_roots": ["input:input"],
  "dataflow_path": ["input", "decide(input)", "command", "DisableMotor"]
}
```

`analysis.input_preimage_version` is `1`.

## Conservative boundaries

The first implementation expands only when all of the following are proven:

- the discriminator subject is a local immutable binding;
- the binding value is a direct named function call;
- the function has typed guarded clauses;
- the compared pattern is a variant of that function's sum return type;
- substituted guard predicates are rooted in machine inputs;
- Action payload refinement is unique when applied.

No arbitrary symbolic execution, recursion expansion, Effect execution, or target-based inference is performed.

## Verification

### Semantic tests

- Motor Safety stop routes use input predicates, Action `DisableMotor`, and Target State `Stopped`.
- Motor Safety run routes use `otherwise`, Action `SetMotorPower(normalize(input.raw))`, and Target State `Running`.
- Door Controller routes use `input.forced_open`, authenticated open request, and `otherwise` with Actions `RaiseAlarm`, `Unlock`, and `KeepLocked`.
- No expanded Input equals its Action variant name.
- Target, Action, Input, and Effect remain pairwise independent.
- Ambiguous or unsupported definitions produce a warning instead of invented provenance.

### Metamorphic tests

- Renaming a state changes Target only.
- Renaming an Action variant changes Action only.
- Rewriting a decision predicate changes Input only.
- Adding an Effect changes `effect_invocations` only.

### README publishing gate

Before a state screenshot can replace the README image, browser and snapshot verification must prove:

- at least one visible transition has non-empty `data-input-value`;
- the same transition has non-empty `data-action-value`;
- the rendered value contains exactly the semantic join `Input [Guard] ➞ Action`;
- Action differs from Target State;
- the Input is not merely the Action variant repeated on the left;
- the public Motor Safety example contains `DisableMotor → Stopped` and `SetMotorPower(...) → Running`;
- the public Motor Safety example does not contain `Stop → Stopped` or `Drive(...) → Running`.

The screenshot remains secondary evidence. The compiler IR and DOM contract tests are the primary evidence.

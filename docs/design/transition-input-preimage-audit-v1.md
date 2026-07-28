# Transition Input Preimage Audit v1

## Purpose

This audit verifies that StateTransitionIR keeps four independent roles:

- **Input**: a predicate rooted in machine input parameters
- **Guard**: a persistent state or invariant condition
- **Action**: the value projected by `machine action=state.field`
- **Target State**: the value projected by `machine select=state.field`

Effects remain separate in `effect_invocations`.

The audit is designed to reject plausible-looking but unsound diagrams. A transition must not lose conditions merely because one intermediate decision value can be expanded.

## Required invariants

For every compiled transition:

1. Target State is never used as Action.
2. Effect invocation is never used as Action.
3. An intermediate sum variant is not claimed as an exact Input without a proven machine-input preimage.
4. Input-preimage expansion is atomic: either the complete trigger is preserved, or the complete proven replacement is installed.
5. A state-dependent predicate is not reclassified as pure Input.
6. Unsupported dataflow is retained as a provisional Input with `STIR_INPUT_PREIMAGE_UNRESOLVED`.
7. Generated block and lambda helper names do not appear in public transition labels.
8. Action payloads are concretized only when every matching decision branch proves the same payload expression.

## Existing examples audited

| Example | Input form | Action | Effect | Expected preimage behavior |
| --- | --- | --- | --- | --- |
| `session_protocol.glyph` | direct sum event | none | none | no rewrite |
| `traffic_light.glyph` | boolean input | none | none | no rewrite |
| `conveyor_control.glyph` | event plus guard | none | `set_conveyor` | no rewrite; Effect remains separate |
| `effect_failure.glyph` | direct event | none | `write_pump` | no rewrite; failure edge keeps Effect separate |
| `valve_nested_effect.glyph` | direct event | none | `write_valve` | no rewrite through nested Effect helper |
| `cooling_fan_effect.glyph` | boolean inputs | none | `write_fan` | distinct provisional routes remain distinct |
| `dual_machines.glyph` | direct events | none | none | no Target-to-Action fallback |
| `door_controller.glyph` | local decision output | explicit Action | none | expand to input predicate |
| `motor_safety.glyph` | local decision output with payload | explicit Action | `write_motor` outside transition Action | expand and refine payload |

## Adversarial cases

### Direct event plus intermediate decision

```text
event == Start & decision == Run
```

Expanding only `decision == Run` would erase `event == Start`. The compiler therefore preserves the combined trigger provisionally and emits `STIR_INPUT_PREIMAGE_UNRESOLVED`.

### Multiple intermediate decisions

```text
route == Go & permission == Allowed
```

Expanding only one decision would be unsound. The compiler performs no partial rewrite.

### State-dependent decision

```text
state.mode == Idle & input.allow >> Run
```

The selected decision output depends on state. It is not a pure machine Input and is therefore not installed as an exact Input preimage.

### Nested unsupported helper

```text
decision := wrapper(input)
```

When `wrapper` cannot be reduced to a supported guarded decision, the existing trigger is downgraded to provisional instead of being reported as exact.

### Immutable decision block

A common function block shape is supported:

```glyph
>decide(input:Input):Command
  normalized :=
    input.raw
    /> |x| min(x,1.0)
  command :=
    !input.enabled >> Stop
    _ >> Drive(normalized)
  command
```

The compiler resolves the final conditional binding, substitutes preceding pure bindings, restores lowered lambda bodies, and publishes the public expression:

```text
otherwise ➞ Drive(min(input.raw,1.0))
```

Internal names such as `__glyph_block_*` are forbidden in the public IR.

## Ordered guard semantics

Guard functions use first-match semantics. For:

```glyph
input.emergency >> Stop
input.request >> Run
_ >> Hold
```

The proven preimages are:

```text
Stop: input.emergency
Run: input.request & !input.emergency
Hold: otherwise
```

The compiler includes negations of prior branches that return a different variant.

## Payload policy

A pattern such as `Drive(speed)` may represent a family of Actions.

- If all matching decision branches bind `speed` to the same expression, the Action is refined to that expression.
- If matching branches produce different payloads, the Action remains symbolic as `Drive(speed)`.
- The compiler must not choose one branch value arbitrarily.

## Test ownership

- `tests/test_transition_input_provenance.py`: primary Input/Action/Target separation
- `tests/test_transition_input_provenance_audit.py`: existing-example matrix and adversarial rejection cases
- `tests/test_transition_input_preimage_generalization.py`: ordered guards, local chains, ambiguous payloads
- `tests/test_transition_block_decision_preimage.py`: immutable block and lambda restoration
- `tests/test_transition_semantics.py`: Effect and failure-path separation
- `tests/verify_state_diagram_rendering.mjs`: DOM-level `Input ➞ Action` publication contract

## Supported proof boundary

The compiler currently proves preimages for:

- one intermediate discriminator that is the complete classified trigger;
- a direct guarded pure function;
- an immutable function block whose final binding is conditional and whose preceding bindings are pure expressions;
- ordered guards with a final fallback;
- payload substitution when all matching branches agree.

The compiler deliberately refuses:

- partial expansion of compound triggers;
- multiple intermediate discriminators in one transition;
- state-dependent preimages;
- nested helpers that cannot be reduced through the supported block structure;
- ambiguous payload concretization;
- symbolic execution of Effects.

Refusal is observable through a provisional trigger and `STIR_INPUT_PREIMAGE_UNRESOLVED`; it is not silent.

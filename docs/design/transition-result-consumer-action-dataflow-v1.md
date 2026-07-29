# Transition Result → Consumer Action Dataflow v1

Status: Superseded

Superseded by:

- `state-transition-action-scopes-v1.md`
- `transition_result_consumer_action_version = 2`

## Historical contract

Version 1 established that a concrete transition result could flow through an immutable caller binding into a downstream operation:

```text
machine next branch
→ caller result binding
→ immutable aliases / pure helpers
→ external operation
→ operation-derived Action
```

It corrected the original `actuator(state)` and missing-Action defects, but it had two structural limitations:

1. it recognized only a narrow direct-binding caller shape;
2. it projected caller operations into the same Action field as intrinsic machine operations.

Those limitations are not part of the current contract.

## Current contract

Version 2 evaluates each declared `system entry` independently and recognizes direct, nested, bound, aliased, and pure-wrapper calls to the machine `next=` function.

Caller operations are published under `execution_action_bindings`. Intrinsic branch operations remain under `machine_action`. A separate `display_action` projection preserves renderer compatibility without redefining system operations as Machine Actions.

Divergent systems remain distinct and require an execution context. They are not collapsed into one guessed Action.

See `state-transition-action-scopes-v1.md` for the complete IR, invariants, diagnostics, Boolean branch reasoning, compatibility policy, and acceptance requirements.

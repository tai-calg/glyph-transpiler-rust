# Transition Source Specialization v1

Status: Implemented

## Problem

A guarded transition function is an ordered decision list. Expanding its final wildcard branch independently for every state creates transitions that cannot execute. Returning the original `state` parameter also leaves downstream Actions such as `actuator(state)` less precise than the compiler can prove.

For example:

```glyph
>step(state:DoorState,input:Input):DoorState
  state.mode==Opening&input.obstruction >> DoorState(Alarm)
  state.mode==Opening >> DoorState(Open)
  _ >> state
```

When the source state is `Opening`, the second branch is unconditional after selector specialization. The later wildcard is unreachable for that source and must not produce an `Opening -> Opening` edge.

## Compilation model

The compiler performs the following private stages before publishing StateTransitionIR:

```text
ordered authored branches
→ specialize selector predicates for each source state
→ reject statically false branches
→ retain input-dependent branches
→ mark a source exhausted after a statically true branch
→ specialize each retained branch result
→ derive Target State, Emitted Output, and operation Action
```

The planner operates per source state rather than expanding a wildcard first and trying to repair the graph afterward.

## Structural state specialization

For a state type with only the selector field:

```glyph
*DoorState(mode:DoorMode)
```

`state` under source `Closed` becomes:

```text
DoorState(Closed)
```

For a state type containing additional runtime fields:

```glyph
*DeviceState(mode:Mode,count:U)
```

`state` under source `Idle` becomes:

```text
DeviceState(Idle,state.count)
```

The selector component is concrete. Other components remain symbolic projections unless their values are independently provable. The compiler does not invent runtime data.

## Action consequence

Given:

```glyph
next := step(state,input)
actuator(next)
```

a retained fallback for `Closed` publishes:

```text
[otherwise] ➞ actuator(DoorState(Closed))
```

It does not publish `actuator(state)`, and it does not substitute the Target State name directly as Action.

## Invariants

1. Branch priority is evaluated independently for every source state.
2. A source state is exhausted only by a condition proven true after source specialization.
3. Input-dependent conditions remain possible and do not exhaust the source.
4. Later branches are omitted only for exhausted source states.
5. `state` is specialized structurally, not replaced by a bare state name.
6. Non-selector fields remain symbolic when not statically known.
7. Target State, Emitted Output, and Action remain separate semantic axes.
8. Downstream operation tracing consumes the same specialized branch value used by transition compilation.
9. Branch extraction, source planning, and branch-value lookup live in one private module.
10. Provenance constants and Action IR construction remain private implementation details.

## Dependency boundaries

- `_transition_branch_semantics.py`: branch extraction, source planning, expression specialization, and branch-value lookup.
- `_transition_action_ir.py`: private provenance values and Action/invocation construction.
- `state_transition_compiler.py`: publishes normalized transition structure.
- `transition_action_projection.py`: derives branch-local operations and emitted outputs.
- `transition_result_action_dataflow.py`: derives caller operations that consume transition results.
- renderer and export layers: consume structured IR only; they perform no semantic inference.

Neither private helper module is re-exported from the package root.

## Acceptance cases

The exact default workspace must produce nine normal transitions:

```text
Closed  -> Opening
Opening -> Alarm
Opening -> Open
Open    -> Closing
Closing -> Opening
Closing -> Closed
Closed  -> Closed
Open    -> Open
Alarm   -> Alarm
```

It must not produce `Opening -> Opening` or `Closing -> Closing`, and no Action may contain `actuator(state)`.

A multi-field state regression must preserve unresolved fields structurally, for example:

```text
actuator(DeviceState(Idle,state.count))
```

Compiler, browser semantic, export, and snapshot suites must pass before merge.

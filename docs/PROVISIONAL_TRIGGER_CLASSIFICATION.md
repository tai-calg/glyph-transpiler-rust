# Trigger / Guard Classification

## Status

Normative implementation specification for StateTransitionIR v3.

Glyph renders state-transition labels using:

```text
trigger [guard] / effect
```

The compiler must not place an input-derived condition in guard brackets merely because it cannot prove that the condition is an event. Ambiguity is non-fatal: the diagram remains available and the condition is shown as a warning-backed provisional trigger.

No new Glyph declaration or keyword is introduced.

## Roles

Each transition condition is classified into one of these roles:

```text
source-state predicate
confirmed trigger
inferred trigger
provisional trigger
guard
unclassified condition
```

### Source-state predicate

A comparison between the machine selector and one of its state variants:

```glyph
state.mode==Locked
```

It determines the arrow source and is not repeated in the label.

### Confirmed trigger

A machine-input finite sum value compared with one of its variants:

```glyph
input.event==RequestOpen
```

Required evidence:

- the compared value has a finite sum type;
- the compared variant belongs to that type;
- the value is rooted in a machine input or external input;
- it is not the machine state selector.

Rendering:

```text
RequestOpen
```

### Inferred trigger

An input-derived finite sum value reached through local bindings or pure helpers:

```glyph
>decide(input:Input):Action
  input.forced_open >> RaiseAlarm
  _ >> KeepLocked

>step(state:DoorState,input:Input):DoorState
  action := decide(input)
  action==RaiseAlarm >> DoorState(Alarmed)
```

The compiler follows:

```text
input → decide(input) → action:Action → RaiseAlarm
```

Rendering:

```text
RaiseAlarm
```

The derivation path is retained in StateTransitionIR and exposed in the UI tooltip.

### Guard

A Boolean constraint that additionally permits a transition after a trigger has been identified, or a state-only condition on a triggerless transition:

```glyph
input.event==RequestOpen
  & input.badge_valid
  & state.failures<3
    >> DoorState(Unlocked)
```

Rendering:

```text
RequestOpen [input.badge_valid&state.failures<3]
```

Only guards receive square brackets.

### Provisional trigger

A condition is input-derived, but the compiler cannot prove whether it represents an occurrence or a persistent condition:

```glyph
input.forced_open >> DoorState(Alarmed)
```

Compilation succeeds. The transition receives a warning and renders on the trigger side:

```text
? input.forced_open
```

It must not render as:

```text
[input.forced_open]
```

A provisional trigger uses a warning color, dashed border and `?` prefix. These indicators remain in exported diagrams.

### Unclassified condition

The compiler cannot resolve either type or provenance:

```text
? unknown==Foo
```

It remains separate from both confirmed guards and provisional input triggers.

## Classification pipeline

StateTransitionIR v3 classification runs after ordinary state lowering and immutable `:=` block lowering, so both code paths share one semantic pass.

```text
machine.next reachability
  → lowered branch conditions
  → local type environment
  → local-definition recovery
  → type and provenance analysis
  → source / trigger / guard classification
  → warning diagnostics
  → StateTransitionIR v3
  → renderer
```

The renderer does not infer semantics. It only displays compiler-produced roles.

## Type and provenance evidence

Each analyzed value records:

```text
ValueInfo {
  type
  definition
  provenance_roots
  dataflow_path
  state_dependency
}
```

Provenance roots include:

```text
input:<parameter>
external:<boundary>
state
unknown:<name>
```

Classification never depends on names such as `event`, `action` or `command`.

## Condition decomposition

For a conjunction:

```glyph
state.mode==Locked
  & input.event==RequestOpen
  & input.badge_valid
  & state.failures<3
```

The compiler classifies atoms in this order:

1. Remove source-state predicates.
2. Extract typed input sum-variant comparisons as confirmed triggers.
3. Extract input-derived local sum-variant comparisons as inferred triggers.
4. Classify remaining known Boolean constraints as guards when a trigger is known.
5. When no trigger is known, combine input-derived ambiguous atoms into one provisional trigger.
6. Retain state-only atoms as guards.
7. Keep unresolved atoms as unclassified conditions.

Result:

```text
source  = Locked
trigger = RequestOpen
guard   = input.badge_valid & state.failures<3
```

## Ambiguous combinations

### One Boolean input

```glyph
input.request_open >> ...
```

```text
? input.request_open
```

Diagnostic:

```text
STIR_TRIGGER_AMBIGUOUS_FALLBACK
```

### Boolean input plus state constraint

```glyph
input.request_open & state.failures<3 >> ...
```

```text
? input.request_open [state.failures<3]
```

### Multiple Boolean inputs with no event discriminator

```glyph
input.request_open & input.badge_valid >> ...
```

The compiler must not arbitrarily choose one as the trigger. It combines them:

```text
? (input.request_open&input.badge_valid)
```

Diagnostic:

```text
STIR_MULTIPLE_TRIGGER_CANDIDATES
```

### Multiple typed event discriminators

```glyph
input.door_event==RequestOpen
  & input.security_event==Authenticated
    >> ...
```

The conjunction is rendered provisionally and warned rather than rejected:

```text
? (RequestOpen&Authenticated)
```

Diagnostic:

```text
STIR_MULTIPLE_CONFIRMED_TRIGGERS
```

## Diagnostics

All ambiguity diagnostics are warnings in normal compilation and interactive editing.

```text
STIR_TRIGGER_AMBIGUOUS_FALLBACK
STIR_MULTIPLE_TRIGGER_CANDIDATES
STIR_MIXED_TRIGGER_GUARD_PREDICATE
STIR_CONDITION_PROVENANCE_UNKNOWN
STIR_MULTIPLE_CONFIRMED_TRIGGERS
```

Warnings must:

- preserve `ready` editor status;
- keep preview, drag, save and export available;
- link to the source branch line;
- explain the result in ordinary language;
- suggest an event sum type where appropriate.

## StateTransitionIR v3

Each transition includes structured semantics:

```json
{
  "trigger": {
    "display": "RequestOpen",
    "expression": "input.event==RequestOpen",
    "role": "confirmed-trigger",
    "confidence": "exact",
    "value_type": "DoorEvent",
    "variant": "RequestOpen",
    "provenance_roots": ["input:input"],
    "dataflow_path": ["input", "input.event"]
  },
  "guards": ["input.badge_valid"],
  "unclassified_conditions": [],
  "action": "unlock(state)"
}
```

Compatibility projections remain available:

```text
event
guard
display_label
```

They are generated from the structured fields and are not the source of truth.

## User-facing progression

A simple Boolean model remains usable:

```glyph
*Input(open:B)
input.open >> ...
```

It renders with one warning:

```text
? input.open
```

A user can later remove the warning by expressing occurrences explicitly:

```glyph
+DoorEvent=Open|Close
*Input(event:DoorEvent)
input.event==Open >> ...
```

It then renders as a confirmed trigger:

```text
Open
```

This is progressive precision, not a prerequisite for first use.

## Invariants

1. Unknown input meaning is never silently converted into a guard.
2. A provisional trigger is never visually indistinguishable from a confirmed trigger.
3. Guard brackets are reserved for compiler-classified guards.
4. Ambiguity alone never prevents compilation or diagram interaction.
5. Equivalent refactoring through local variables or pure helpers preserves classification.
6. Renderer code never reclassifies conditions.
7. Saved label positions use transition IDs, not display strings.

## Regression requirements

Tests must cover:

- confirmed sum-type input triggers;
- inferred triggers through block-local values;
- warning-backed Boolean input triggers;
- provisional input plus state guard separation;
- confirmed trigger plus Boolean input guard;
- distinct provisional failure paths;
- warning source-line remapping;
- renderer `?` prefix and dashed style;
- no brackets around provisional triggers;
- brackets around actual guards;
- browser and export preservation;
- compatibility fields and v2 readiness event.

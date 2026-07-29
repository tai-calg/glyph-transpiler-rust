# Transition Enabling Case Semantics v1

Status: Implementing

## 1. Scope

This document defines how Glyph compiles and renders the conditions under which a state transition is enabled.

It does **not** add surface syntax. Existing Glyph syntax remains unchanged.

The design replaces the ambiguous internal term `route` with the precise term **Enabling Case** (`enabling_case`).

## 2. Normative vocabulary

All terms in this section are normative. Implementations and tests must use these meanings.

### 2.1 State Machine

A **State Machine** is a Glyph `machine` declaration together with its state value, selector, next-state computation, optional Action projection, success state, and failure state.

### 2.2 Transition

A **Transition** is one compiler-derived relationship from a Source State to a Target State, optionally carrying an Action and Effects.

A Transition is not an Enabling Case. One Transition may contain one or more Enabling Cases.

### 2.3 Source State

The **Source State** is the state from which a Transition is evaluated.

A selector equality that merely restates the Source State is structural state-machine information. It is not rendered again as an Input Pattern or Guard.

### 2.4 Target State

The **Target State** is the state value projected by `machine select=` after the transition computation.

Target State is never inferred from Action.

### 2.5 Input Root

An **Input Root** is a machine parameter other than the state parameter, or a declared external input source.

Examples:

```text
input
request
external:button_pressed
```

Input Root describes data provenance. It does not by itself determine whether an expression is an Input Pattern or a Guard.

### 2.6 Input Atom

An **Input Atom** is a direct pattern over an Input Root that identifies accepted input values.

Supported exact forms in v1 are:

```text
input.field
!input.field
input.field == value
input.field != value
input.field < value
input.field <= value
input.field > value
input.field >= value
input.variant == Variant
external_event()
```

A named pure predicate such as `authenticate(input)` is not an Input Atom merely because it depends on input data.

### 2.7 Input Pattern

An **Input Pattern** is the conjunction or disjunction of Input Atoms authored for one Enabling Case.

It answers:

> Which input value or input pattern selects this case?

An Input Pattern may be absent.

An expression is not classified as Input Pattern solely from input provenance. Direct-pattern shape and authored origin are required.

### 2.8 Guard

A **Guard** is an additional proposition that must hold after the Input Pattern matches for the Enabling Case to be enabled.

A Guard may depend on Input Roots, state, time, or pure derived predicates.

Examples:

```text
!input.fault
state.ready
authenticate(input)
@E 100ms input.stopped
otherwise
```

Therefore, `input-derived` and `Guard` are not opposites.

### 2.9 Authored Guard

An **Authored Guard** is a Guard term written by the Glyph author in the source clause.

Example:

```glyph
input.request_open & authenticate(input) >> Unlock
```

compiles to:

```text
Input Pattern = input.request_open
Authored Guard = authenticate(input)
```

### 2.10 Generated Guard

A **Generated Guard** is a Guard term added by the compiler to preserve the exact semantics of ordered clauses, fallback, temporal lowering, or another proven compiler transformation.

Generated Guard terms must record their origin.

### 2.11 Priority Exclusion

A **Priority Exclusion** is a Generated Guard that excludes earlier ordered clauses whose result differs from the current result.

For:

```glyph
input.fault >> LatchFault
input.emergency >> EmergencyBrake
```

the second clause has:

```text
Input Pattern = input.emergency
Priority Exclusion = !input.fault
```

Priority Exclusion is never merged into Input Pattern.

### 2.12 Fallback

A **Fallback** is the final `_` clause of an ordered decision.

Fallback is not an Input Pattern and is not an event.

It is represented as a Guard term with:

```text
kind = fallback
origin = fallback
rendered display = otherwise
```

The exact complement of prior clauses is retained in Exact Enabling Condition.

### 2.13 Enabling Case

An **Enabling Case** is one alternative condition case that enables a Transition.

It contains:

```text
Input Pattern
Guard
Exact Enabling Condition
provenance
confidence
```

The Japanese normative name is **遷移成立ケース**.

The IR name is `enabling_case`; the collection name is `enabling_cases`.

The term `route` must not be used for this concept because it is confusable with graph paths and edge routing.

### 2.14 Exact Enabling Condition

The **Exact Enabling Condition** is the complete Boolean expression under which an Enabling Case is semantically active after ordered-clause semantics are applied.

For each exact Enabling Case:

```text
Exact Enabling Condition ≡ Input Pattern ∧ Guard
```

When Input Pattern is absent, it is treated as `true` for this equivalence.

When Guard is absent, it is treated as `true`.

For Fallback, the displayed Guard is `otherwise`, while the exact complement remains in `exact_enabling_condition.expression`.

### 2.15 Action

An **Action** is the operation value projected only by `machine action=`.

Action is not Target State and is not Effect.

### 2.16 Effect

An **Effect** is an external or effectful invocation recorded in `effect_invocations`.

Effect is never used as Action, Input Pattern, Guard, or Target State.

### 2.17 Provenance

**Provenance** records where an IR value came from.

Required origins for Guard terms are:

```text
authored-derived-predicate
state-condition
priority-exclusion
temporal-condition
fallback
unknown
```

Required origins for Input Patterns are:

```text
authored-direct-input-pattern
authored-event-pattern
provisional-input-pattern
```

### 2.18 Confidence

**Confidence** is the compiler's level of proof for a classification.

Values are:

```text
exact
inferred
provisional
unknown
```

`provisional` is a warning-bearing compatibility result, not an error.

### 2.19 Provisional Input Pattern

A **Provisional Input Pattern** is an input-derived authored predicate whose occurrence or direct-pattern semantics cannot be proven.

Example:

```glyph
is_requested(input) >> Open
```

When no more precise classification is possible, it is retained on the Input side with `provisional` confidence and a warning, preserving the established UX rule.

It must be visually distinguishable from exact Input Pattern.

### 2.20 Unclassified Condition

An **Unclassified Condition** is a condition whose origin or role cannot be safely assigned without changing semantics.

It remains explicit in IR and causes a warning. It must not be silently moved into Input Pattern or Guard.

### 2.21 Compatibility Projection

A **Compatibility Projection** derives the legacy fields `trigger`, `guards`, `event`, and `guard` from `enabling_cases` for old consumers.

`enabling_cases` is the semantic source of truth.

### 2.22 Lossy Compatibility Projection

A **Lossy Compatibility Projection** occurs when multiple Enabling Cases cannot be represented faithfully by the single legacy `trigger` plus `guards` shape.

The transition must then contain:

```json
"legacy_projection_lossy": true
```

No renderer implementing this specification may use the lossy legacy fields as its semantic source.

## 3. Reserved and user-defined terms

The following are compiler/IR terms and are not new Glyph keywords:

```text
enabling_case
enabling_cases
input_pattern
guard_terms
exact_enabling_condition
legacy_projection_lossy
priority-exclusion
fallback
```

The following remain user-defined identifiers:

```text
state type names
state variants
Action type names
Action variants
parameter names
function names
field names
```

No new surface-language reserved word is introduced.

## 4. Semantic model

A Transition contains zero or more Enabling Cases:

```text
Transition =
  Source State
  × Target State
  × Action?
  × Effects*
  × Enabling Case+
```

One Enabling Case is:

```text
Enabling Case =
  Input Pattern?
  × Guard Terms*
  × Exact Enabling Condition
  × Provenance
  × Confidence
```

The transition is enabled when at least one Enabling Case is enabled:

```text
E_transition = E_case_1 ∨ E_case_2 ∨ ... ∨ E_case_n
```

## 5. Why one transition may require multiple Enabling Cases

The expression:

```text
(input.a & state.ready) | input.b
```

cannot be faithfully represented as one global `Input [Guard]` pair without changing meaning.

It is represented as:

```text
Case 1: input.a [state.ready]
Case 2: input.b
```

The compiler may use bounded disjunctive-normal-form expansion.

Limits in v1:

```text
maximum enabling cases per source expression = 16
maximum condition atoms per source expression = 64
```

If a limit is exceeded, the compiler emits `STIR_ENABLING_CASE_DECOMPOSITION_UNRESOLVED` and preserves a provisional condition without inventing a decomposition.

## 6. Classification rules

### 6.1 Direct Input Atom

An authored atom is Input Pattern when all conditions hold:

1. it is one of the exact direct forms defined in Input Atom;
2. its subject is rooted directly in a machine or external input;
3. it is not compiler-generated;
4. it does not also depend on state or unknown values.

### 6.2 Derived authored predicate

An authored call or compound predicate such as `authenticate(input)` is Guard when another direct Input Atom exists in the same Enabling Case.

When it is the only input-derived authored predicate, it becomes Provisional Input Pattern with a warning.

### 6.3 State-derived condition

A state-derived condition is Guard, except for the selector equality already represented by Source State.

### 6.4 Priority semantics

Every exclusion generated from an earlier ordered clause is Guard with `origin=priority-exclusion`.

It must never be folded into Input Pattern.

### 6.5 Fallback semantics

Fallback has no Input Pattern.

Its display Guard is `otherwise`.

Its Exact Enabling Condition stores the precise complement of earlier clauses.

### 6.6 Unknown provenance

Unknown provenance is never silently classified.

It remains in `unclassified_conditions` and emits a warning.

## 7. StateTransitionIR extension

The core StateTransitionIR schema remains version 4 for compatibility. This feature has an independent extension version:

```json
"transition_enabling_case_version": 1
```

Each transition gains:

```json
{
  "enabling_cases": [
    {
      "id": "T2:C1",
      "input_pattern": {
        "display": "input.emergency",
        "expression": "input.emergency",
        "kind": "direct-input-pattern",
        "origin": "authored-direct-input-pattern",
        "confidence": "exact",
        "provenance_roots": ["input:input"],
        "source_line": 36
      },
      "guard_terms": [
        {
          "display": "!input.fault",
          "expression": "!input.fault",
          "kind": "predicate",
          "origin": "priority-exclusion",
          "confidence": "exact",
          "source_line": 35
        }
      ],
      "guard": {
        "display": "!input.fault",
        "expression": "!input.fault"
      },
      "exact_enabling_condition": {
        "expression": "input.emergency&!input.fault",
        "proven_exact": true
      },
      "fallback": false,
      "confidence": "exact"
    }
  ],
  "legacy_projection_lossy": false
}
```

## 8. Compatibility projection

For exactly one Enabling Case:

```text
trigger = input_pattern
 guards = guard_terms displays
 event = trigger display
 guard = conjunction of guard term displays
```

For Fallback:

```text
trigger = null
 guards = ["otherwise"]
 event = null
 guard = "otherwise"
```

For multiple Enabling Cases:

```text
legacy_projection_lossy = true
```

Legacy fields may remain populated for old consumers, but new renderers must use `enabling_cases`.

## 9. Rendering contract

One Enabling Case is rendered as:

```text
Input Pattern [Guard] ➞ Action
```

Omission rules:

```text
Input only:       Input Pattern ➞ Action
Guard only:       [Guard] ➞ Action
Input and Guard:  Input Pattern [Guard] ➞ Action
Fallback:         [otherwise] ➞ Action
No Action:        Input Pattern [Guard]
```

A transition with multiple Enabling Cases renders one semantic line per case, sharing the same Action and Target State.

The renderer must expose separate DOM attributes:

```text
data-input-value
data-guard-value
data-action-value
data-exact-enabling-condition
data-enabling-case-id
```

The renderer must not reconstruct Input Pattern or Guard from display text.

## 10. Motor Safety normative result

For:

```glyph
input.fault >> LatchFault
input.emergency >> EmergencyBrake
!input.enabled >> DisableMotor
_ >> SetMotorPower(normalize(input.raw))
```

The required result is:

```text
input.fault ➞ LatchFault
input.emergency [!input.fault] ➞ EmergencyBrake
!input.enabled [!(input.fault|input.emergency)] ➞ DisableMotor
[otherwise] ➞ SetMotorPower(normalize(input.raw))
```

Forbidden results include:

```text
input.emergency&!input.fault ➞ EmergencyBrake
!input.enabled&!(input.fault|input.emergency) ➞ DisableMotor
otherwise ➞ SetMotorPower(...)
```

because they respectively merge Generated Guard into Input Pattern or misclassify Fallback as Input.

## 11. Diagnostics

Required new diagnostics:

```text
STIR_ENABLING_CASE_DECOMPOSITION_UNRESOLVED
STIR_ENABLING_CASE_PROVISIONAL_INPUT
STIR_ENABLING_CASE_MEANING_NOT_PRESERVED
STIR_ENABLING_CASE_LEGACY_PROJECTION_LOSSY
```

All are warnings in v1. `_` fallback itself is normal and does not produce a warning.

## 12. Verification contract

### 12.1 Compiler tests

The test suite must prove:

1. Priority Exclusion changes Guard only.
2. Adding or removing a prior clause does not alter the authored Input Pattern.
3. Fallback has `input_pattern=null` and Guard `otherwise`.
4. A derived predicate beside a direct input becomes Authored Guard.
5. A state-derived predicate becomes Guard.
6. A lone ambiguous input-derived predicate becomes Provisional Input Pattern with warning.
7. A non-separable OR becomes multiple Enabling Cases.
8. Multiple clauses producing one Action remain separate Enabling Cases.
9. Synthesized failure does not fabricate an Enabling Case.
10. Action, Target State, and Effects are unchanged by Input/Guard decomposition.

### 12.2 Meaning-preservation tests

For Boolean expressions within the bounded verifier domain, tests enumerate all assignments and prove:

```text
Exact Enabling Condition == Input Pattern ∧ Guard
```

### 12.3 Metamorphic test

Before:

```glyph
input.emergency >> EmergencyBrake
```

After:

```glyph
input.fault >> LatchFault
input.emergency >> EmergencyBrake
```

Required invariant:

```text
Input Pattern remains input.emergency
Guard changes from empty to !input.fault
Action remains EmergencyBrake
Target State remains Stopped
```

### 12.4 Browser contract

For the EmergencyBrake case:

```text
data-input-value = input.emergency
data-guard-value = !input.fault
data-action-value = EmergencyBrake
```

The combined exact expression must not appear in `data-input-value`.

### 12.5 Snapshot contract

PNG comparison is secondary evidence. Compiler IR and DOM contracts must pass first.

## 13. Implementation order

1. Commit this terminology and IR contract.
2. Add failing compiler tests.
3. Implement Enabling Case derivation.
4. Add compatibility projection.
5. Make browser rendering consume `enabling_cases`.
6. Add DOM and meaning-preservation tests.
7. Regenerate README snapshot only after all semantic tests pass.

## 14. Non-goals

v1 does not:

- add new Glyph syntax;
- infer arbitrary natural-language event semantics;
- classify by identifier names;
- make ambiguity a compile error;
- treat fallback as an error;
- remove legacy fields;
- use renderer heuristics to recover compiler semantics.

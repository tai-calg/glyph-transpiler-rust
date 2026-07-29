# Transition Enabling Cases v1

Status: Implemented

## 1. Purpose

This specification defines the semantic boundary between Input Pattern and Guard in a state transition. It prevents a compiler-derived exact enabling condition from being rendered as though the entire expression were an Input.

Action-source semantics are defined by `transition-operation-action-semantics-v2.md`. No new Glyph syntax is introduced.

## 2. Terms

### 2.1 State

A value of the field selected by `machine select=`. A state is rendered as a node.

### 2.2 Source State

The state from which a transition originates. A selector equality that merely restates the Source State is structural and is not repeated as a Guard.

### 2.3 Target State

The state reached by a transition. It is obtained only from the `machine select=` projection of the transition result.

### 2.4 Emitted Output

A data value projected from the transition result by the legacy `machine action=state.field` selector. It may identify a decision result or command transported by the state value. It is not an Action.

### 2.5 Operation Invocation

A compiler-recognized executable call occurring in the transition branch.

### 2.6 Action

One or more Operation Invocations executed by the transition branch. Action is not derived from Source State, Target State, Emitted Output, or naming similarity.

### 2.7 Effect

The side-effect and failure properties of an Operation Invocation. An effectful invocation can simultaneously be an Action occurrence and an Effect occurrence because the terms describe different axes.

### 2.8 Authored Clause

One ordered branch written by the user in a guarded function or conditional block. Its predicate is the Authored Predicate. `_` is the Fallback Clause.

### 2.9 Input Root

A machine input parameter or declared external input source from which an expression derives data.

### 2.10 Direct Input Atom

An authored atomic predicate that directly observes an Input Root without calling a decision predicate. Supported forms include:

- `input.flag`
- `!input.flag`
- `input.field == value`
- `input.field != value`
- `input.field < value`, `<=`, `>`, `>=`
- an external zero-argument event source

A function call such as `authenticate(input)` is not a Direct Input Atom even though it is input-derived.

### 2.11 Input Pattern

The authored direct observation that identifies the accepted region of the input space for one Enabling Case. Input Pattern is derived only from Direct Input Atoms in the Authored Predicate.

Input Pattern is not the complete condition under which a branch wins.

### 2.12 Guard

An additional proposition that must hold after the Input Pattern matches. Guard Terms have an explicit origin:

- `authored-derived-predicate`: authored predicate that is not a Direct Input Atom
- `state-condition`: authored state-derived condition other than the structural Source State
- `priority-exclusion`: compiler-generated exclusion of earlier ordered clauses
- `temporal-condition`: temporal restriction
- `fallback`: ordered fallback selection
- `unknown`: conservatively retained unresolved condition

A Guard may be input-derived. Data provenance alone does not determine semantic role.

### 2.13 Priority Exclusion

For ordered clauses `P1 >> V1`, `P2 >> V2`, ..., clause `k` is eligible only when no earlier clause with a different result wins. The compiler-generated proposition excluding such earlier clauses is the Priority Exclusion. It is always a Guard, never an Input Pattern.

### 2.14 Enabling Condition

The exact Boolean condition under which one Enabling Case wins after ordered-branch semantics are applied.

For a non-fallback case:

```text
EnablingCondition = InputPattern ∧ Guard
```

Absent terms denote `true`.

### 2.15 Enabling Case

One alternative semantic case under which a Transition is enabled. IR name: `enabling_case`; collection name: `enabling_cases`.

An Enabling Case contains:

- zero or one Input Pattern
- zero or more Guard Terms
- one exact Enabling Condition
- provenance and confidence

Multiple authored clauses that produce the same transition result remain separate Enabling Cases. They are not collapsed into an opaque disjunction.

### 2.16 Fallback Enabling Case

An Enabling Case produced by `_`. It has no Input Pattern. Its Guard contains a `fallback` term rendered as `otherwise`; its exact Enabling Condition stores the complement of preceding clauses.

`otherwise` is never an Input.

### 2.17 Provisional Input Pattern

An authored input-derived expression whose occurrence-versus-condition role cannot be proven. It is retained on the Input side with `confidence=fallback`, prefixed by `?`, and accompanied by a diagnostic.

### 2.18 Unclassified Condition

A condition whose type or provenance cannot be resolved and whose placement in Input Pattern or Guard cannot be proven. It remains explicit in IR and produces a warning. It must not be silently dropped.

### 2.19 Legacy Projection

The compatibility fields `trigger`, `guards`, `event`, and `guard` synthesized from `enabling_cases`. New renderers consume `enabling_cases` as the source of truth. If multiple cases cannot be represented losslessly by the legacy fields, `legacy_projection_lossy=true`.

## 3. Core invariants

1. Input Pattern contains only authored input-selection semantics.
2. Priority Exclusion is always a Guard.
3. Fallback is always a Guard and has no Input Pattern.
4. The compiler never replaces Input Pattern with the complete Enabling Condition.
5. Every exact Enabling Case preserves `EnablingCondition ≡ InputPattern ∧ Guard`.
6. Multiple alternative cases remain distinct.
7. Renderer code does not infer Input or Guard from strings.
8. Input Pattern, Guard, Action, Emitted Output, Effect, and Target State remain separate IR roles.
9. Action is operation-derived only.
10. Unknown information is retained provisionally or unclassified; it is never invented or discarded.
11. Existing Glyph source syntax remains valid.

## 4. IR contract

StateTransitionIR remains version 4 for reader compatibility. The additive `transition_enabling_cases_version=1` contract allows each transition to contain:

```json
{
  "enabling_cases": [
    {
      "id": "T2:C1",
      "input_pattern": {
        "display": "input.emergency",
        "expression": "input.emergency",
        "kind": "direct-input-pattern",
        "confidence": "exact",
        "provenance_roots": ["input:input"],
        "source_origin": "authored-clause"
      },
      "guard": {
        "display": "!input.fault",
        "expression": "!input.fault",
        "terms": [
          {
            "display": "!input.fault",
            "expression": "!input.fault",
            "origin": "priority-exclusion"
          }
        ]
      },
      "enabling_condition": {
        "display": "input.emergency&!input.fault",
        "expression": "input.emergency&!input.fault",
        "proven_exact": true
      },
      "fallback": false,
      "confidence": "exact"
    }
  ],
  "emitted_output": {
    "display": "EmergencyBrake"
  },
  "action": {
    "display": "write_motor(EmergencyBrake)",
    "provenance": "transition-operation-invocation"
  },
  "target_state": "Stopped",
  "legacy_projection_lossy": false
}
```

## 5. Decomposition rules

### 5.1 Conjunction

An authored conjunction is flattened into atoms. Direct Input Atoms form Input Pattern. All other atoms become Guard Terms according to origin.

```text
input.request & authenticate(input) & state.ready
```

becomes:

```text
Input Pattern = input.request
Guard = authenticate(input) & state.ready
```

### 5.2 Disjunction

A disjunction containing only Direct Input Atoms may remain one Input Pattern.

A mixed disjunction is converted to bounded disjunctive cases. Limits:

- maximum 16 cases
- maximum 64 atoms

If bounded decomposition cannot preserve semantics, the compiler emits `STIR_INPUT_GUARD_DECOMPOSITION_UNRESOLVED` and preserves the expression provisionally.

### 5.3 Ordered clauses

For clause `k`, the authored predicate is decomposed independently. The complement of prior different-result predicates is added only to Guard as `priority-exclusion`.

### 5.4 Fallback

A fallback clause creates:

```text
Input Pattern = null
Guard.display = otherwise
Enabling Condition = complement of preceding different-result predicates
```

### 5.5 Source-state selector

A predicate equal to the structural Source State is omitted from Guard because it is already represented by the source node. Other state conditions remain Guards.

## 6. Rendering contract

For each Enabling Case:

```text
Input Pattern [Guard] ➞ Action
```

Formatting:

- Input and Guard present: `I [G] ➞ A`
- Input only: `I ➞ A`
- Guard only: `[G] ➞ A`
- Fallback: `[otherwise] ➞ A`
- Provisional Input: `? I [G] ➞ A`
- No operation Action: omit `➞ A`

Emitted Output is not rendered in the Action position.

## 7. Motor Safety expected semantics

For decision clauses:

```glyph
input.fault >> LatchFault
input.emergency >> EmergencyBrake
!input.enabled >> DisableMotor
_ >> SetMotorPower(normalize(input.raw))
```

and branch operations:

```glyph
write_motor(LatchFault)
write_motor(EmergencyBrake)
write_motor(DisableMotor)
write_motor(SetMotorPower(power))
```

expected labels are:

```text
input.fault ➞ write_motor(LatchFault)
input.emergency [!input.fault] ➞ write_motor(EmergencyBrake)
!input.enabled [!(input.fault|input.emergency)] ➞ write_motor(DisableMotor)
[otherwise] ➞ write_motor(SetMotorPower(normalize(input.raw)))
```

The command values remain in `emitted_output`; the operation calls occupy Action.

## 8. Diagnostics

- `STIR_INPUT_GUARD_DECOMPOSITION_UNRESOLVED`
- existing provisional-trigger diagnostics remain supported during compatibility migration

Diagnostics are warnings unless the compiler would otherwise lose semantics.

## 9. Verification contract

Required tests:

1. Priority exclusion changes Guard only.
2. Fallback has null Input Pattern and `[otherwise]` Guard.
3. Input-derived function predicates become Guard.
4. State-derived predicates become Guard.
5. Multiple same-result clauses remain separate Enabling Cases.
6. Mixed OR is decomposed or reported without semantic loss.
7. Exact condition equals Input Pattern conjoined with Guard for supported Boolean cases.
8. Input, Guard, Emitted Output, Action, and Target changes affect only their respective axes.
9. DOM exposes separate `data-input-value`, `data-guard-value`, and `data-action-value` from structured IR.
10. DOM Action equals a proven operation invocation and differs from Target State and Emitted Output.
11. README PNG is regenerated only after IR and DOM contracts pass.

## 10. Migration

- StateTransitionIR v4 readers continue through Legacy Projection.
- Enabling-case-aware renderers consume `enabling_cases` when `transition_enabling_cases_version >= 1`.
- Operation-aware renderers consume only operation-derived `action` when `transition_operation_action_version >= 2`.
- `trigger` and `guards` are compatibility outputs, not semantic inputs.
- `machine action=` remains source-compatible but represents an Emitted Output projection.
- No parser or source-language grammar change is included.

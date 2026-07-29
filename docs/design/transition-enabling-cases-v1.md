# Transition Enabling Cases v1

Status: Implementing in PR #53

## 1. Scope

This design defines how Glyph compiles a transition condition into independent semantic roles for state-diagram rendering and machine-readable IR.

It does not add user-facing syntax. Existing Glyph source remains valid.

The design replaces the previous assumption that one transition has one undifferentiated `trigger` expression. A transition may have one or more **Enabling Cases**, and every Enabling Case keeps authored input selection separate from additional guards introduced by the author, state context, temporal constraints, or ordered-branch semantics.

## 2. Normative vocabulary

The words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative.

### 2.1 Machine

A declared state machine with a state parameter, a selector projection, an optional Action projection, an initial value, and a next-state function.

### 2.2 Source State

The selector value from which a compiled transition originates. A selector equality used only to identify the Source State is represented by the source node and MUST NOT be repeated as a Guard.

### 2.3 Target State

The selector value produced by a transition. Target State is derived only from `machine select=` and MUST NOT populate Action.

### 2.4 Action

The operation value projected by `machine action=`. Action is part of the transition result. It is not an Input Pattern, Guard, Target State, or Effect.

### 2.5 Effect

An invocation crossing an effect boundary. Effects remain in `effect_invocations` and MUST NOT populate Action.

### 2.6 Authored Clause

One ordered guarded clause written by the user in a pure decision function or lowered block. Its predicate is the **Authored Predicate**. `_` is an authored fallback clause with no Authored Predicate.

### 2.7 Ordered Branch Semantics

For clauses `C1`, `C2`, ... in source order, clause `Cn` is selected only when its Authored Predicate is true and every earlier clause producing a different result variant is false.

### 2.8 Priority Exclusion

A compiler-generated Guard excluding earlier clauses that would otherwise win under ordered branch semantics. Priority Exclusion is never an Input Pattern, even when it references machine input.

### 2.9 Input Pattern

The authored portion of one Enabling Case that selects values or variants from machine input or declared external input.

An Input Pattern describes *which input value or input pattern is being accepted*. It does not mean “every Boolean expression that depends on input”.

Direct Input Pattern forms include:

- a Boolean input field, such as `input.fault`;
- a negated Boolean input field, such as `!input.enabled`;
- a comparison whose subject is a direct input field, such as `input.mode==Manual` or `input.raw>0.8`;
- a confirmed external event or typed input variant;
- Boolean combinations composed entirely of direct Input Pattern forms.

### 2.10 Provisional Input Pattern

An input-derived predicate whose occurrence-versus-condition role cannot be proven. It is retained on the Input side for compatibility with the established user-experience rule, but is marked provisional and MUST produce a diagnostic.

Example: a standalone `is_requested(input)` where no direct input pattern exists and the compiler cannot prove event semantics.

### 2.11 Guard

A proposition that must hold in addition to an Input Pattern for an Enabling Case to be active.

A Guard MAY depend on input. Data origin alone does not decide the role.

Guard origins are:

- `authored-derived-predicate`: authored predicate logic that is not a direct Input Pattern, for example `authenticate(input)`;
- `state-condition`: authored logic derived from state, excluding the Source State selector equality;
- `priority-exclusion`: compiler-generated exclusion of earlier ordered clauses;
- `temporal-condition`: temporal constraint;
- `fallback`: the semantic fallback marker `otherwise`;
- `unknown`: preserved unresolved logic.

### 2.12 Exact Enabling Condition

The complete Boolean condition under which one Enabling Case is selected after ordered-branch semantics are applied.

For a non-fallback case:

```text
ExactEnablingCondition = InputPattern AND Guard
```

where absent Input Pattern or Guard is Boolean true.

For a fallback case, the displayed Guard is `otherwise`, while `semantic_expression` stores the exact complement of earlier clauses.

### 2.13 Enabling Case

One alternative condition case under which a Transition performs the same Action and reaches the same Target State.

An Enabling Case contains:

- zero or one Input Pattern;
- zero or more Guard terms;
- one Exact Enabling Condition;
- provenance and confidence metadata.

IR names:

- plural: `enabling_cases`;
- singular concept: `enabling_case`.

The term `Route` is not used because it can be confused with a graph path.

### 2.14 Transition

A relation from Source State to Target State with optional Action and Effects, enabled by one or more Enabling Cases.

```text
Transition = SourceState × EnablingCases × Action × TargetState × Effects
```

### 2.15 Unclassified Condition

A condition whose semantic origin or role cannot be proven. It MUST NOT be silently forced into Input Pattern or Guard. It is preserved with a warning.

### 2.16 Legacy Projection

A compatibility view deriving old `trigger`, `guards`, `event`, and `guard` fields from `enabling_cases`. The legacy projection is not authoritative. If multiple Enabling Cases cannot be represented without loss, `legacy_projection_lossy` MUST be true.

## 3. Semantic invariants

1. `enabling_cases` is the authoritative condition model.
2. Renderers MUST read `enabling_cases` before legacy fields.
3. An Authored Predicate and a Priority Exclusion MUST remain separate AST values.
4. A complete preimage expression MUST NOT overwrite Input Pattern.
5. `otherwise` MUST be represented as a fallback Guard, never as Input Pattern.
6. Input-derived logic MAY be a Guard.
7. Source State selector equality MUST NOT be rendered as Guard.
8. Action, Target State, Input Pattern, Guard, and Effect are independent roles.
9. Every exact case MUST preserve the semantics of the source ordered clauses.
10. Synthesized failure transitions MUST NOT fabricate authored Input Patterns or independence witnesses.
11. String splitting MUST NOT be used to classify expressions; classification operates on AST.
12. Ambiguity MUST be explicit through confidence and diagnostics.

## 4. IR contract

StateTransitionIR version becomes `5`.

Every transition MAY contain:

```json
{
  "enabling_cases_version": 1,
  "enabling_cases": [
    {
      "id": "T2:C1",
      "input_pattern": {
        "display": "emergency=true",
        "expression": "input.emergency",
        "kind": "direct-input-pattern",
        "confidence": "exact",
        "provenance_roots": ["input:input"],
        "origin": "authored-clause"
      },
      "guard": {
        "display": "fault=false",
        "expression": "!input.fault",
        "terms": [
          {
            "display": "fault=false",
            "expression": "!input.fault",
            "semantic_expression": "!input.fault",
            "origin": "priority-exclusion"
          }
        ]
      },
      "enabling_condition": {
        "expression": "input.emergency&!input.fault",
        "proven_exact": true
      },
      "fallback": false,
      "unclassified_conditions": []
    }
  ],
  "legacy_projection_lossy": false
}
```

### 4.1 Input Pattern object

Required fields:

- `display`;
- `expression`;
- `kind`;
- `confidence`;
- `provenance_roots`;
- `origin`.

Allowed `kind` values:

- `direct-input-pattern`;
- `typed-input-variant`;
- `external-event`;
- `provisional-input-pattern`.

### 4.2 Guard object

`guard` is null when no Guard exists. Otherwise it contains:

- `display`: conjunction of term displays;
- `expression`: conjunction of semantic term expressions;
- `terms`: ordered Guard terms.

### 4.3 Guard term object

Required fields:

- `display`;
- `expression`;
- `semantic_expression`;
- `origin`.

A fallback term has:

```json
{
  "display": "otherwise",
  "expression": "otherwise",
  "semantic_expression": "!(earlier clauses)",
  "origin": "fallback"
}
```

### 4.4 Exact Enabling Condition

`enabling_condition.expression` stores the exact compiled condition. `proven_exact` is true only when the compiler constructed the case without dropping or inventing conditions.

### 4.5 Multiple Enabling Cases

Alternative authored clauses or non-factorable disjunctions remain separate cases. They MUST NOT be collapsed into a single Input Pattern with a Guard that changes meaning.

## 5. Decomposition algorithm

### 5.1 Preserve clause components

For every matching decision clause, the compiler retains separately:

- substituted Authored Predicate;
- generated Priority Exclusion;
- exact conjunction;
- source line and result variant.

### 5.2 DNF expansion

The Authored Predicate is converted to bounded disjunctive normal form.

Limits:

- maximum 16 Enabling Cases per transition;
- maximum 64 predicate atoms.

When limits are exceeded, the compiler emits `STIR_INPUT_GUARD_DECOMPOSITION_UNRESOLVED` and preserves a provisional condition rather than expanding unboundedly.

### 5.3 Atom classification

For each conjunction:

- direct input atoms become Input Pattern;
- state-derived atoms become `state-condition` Guard terms;
- calls or derived predicates depending on input become `authored-derived-predicate` Guard terms when a direct Input Pattern exists;
- generated exclusions become `priority-exclusion` Guard terms;
- temporal predicates become `temporal-condition` Guard terms;
- unresolved atoms remain unclassified.

If no direct Input Pattern exists and the authored expression is solely input-derived but occurrence semantics are unknown, it becomes a Provisional Input Pattern.

### 5.4 OR semantics

`input.a|input.b` may remain one Input Pattern when every disjunct is a direct input pattern and no Guard differs.

`(input.a&state.ready)|input.b` becomes two Enabling Cases:

```text
input.a [state.ready]
input.b
```

### 5.5 Ordered clauses

For:

```glyph
a >> A
b >> B
c >> C
```

compiled cases are:

```text
A: Input=a, Guard=none
B: Input=b, Guard=!a
C: Input=c, Guard=!(a|b)
```

Priority exclusions are never folded into Input Pattern.

### 5.6 Fallback

For `_ >> Action`:

- `input_pattern` is null;
- Guard display is `otherwise`;
- Guard semantic expression is the exact complement of earlier clauses.

## 6. Rendering contract

Canonical rendering is:

```text
Input Pattern [Guard] ➞ Action
```

Omission rules:

- Input only: `Input Pattern ➞ Action`;
- Guard only: `[Guard] ➞ Action`;
- fallback: `[otherwise] ➞ Action`;
- no Action: omit `➞ Action`;
- multiple cases: one case per visual line, with Action rendered once after the case group or repeated consistently in exports.

The DOM MUST expose, for each case:

- `data-enabling-case-id`;
- `data-input-value`;
- `data-guard-value`;
- `data-enabling-condition`;
- `data-action-value`.

## 7. Display normalization

Display normalization changes presentation only, never semantic expressions.

Examples:

```text
input.fault                  -> fault=true
!input.enabled               -> enabled=false
input.mode==Manual           -> mode=Manual
!input.fault                 -> fault=false
!(input.fault|input.emergency) -> fault=false & emergency=false
```

When removing an input parameter prefix would be ambiguous because multiple input roots have the same field name, the prefix is retained.

## 8. Compatibility

Legacy fields remain during v5 migration:

- `trigger` is projected from the first Enabling Case Input Pattern;
- `guards` is projected from the first Enabling Case Guard terms;
- `event` and `guard` follow those projections;
- `legacy_projection_lossy=true` when there are multiple cases or unclassified conditions.

New renderers MUST NOT use legacy fields when `enabling_cases_version==1`.

## 9. Diagnostics

- `STIR_INPUT_GUARD_DECOMPOSITION_UNRESOLVED`: bounded or semantic decomposition failed;
- `STIR_PROVISIONAL_INPUT_PATTERN`: an input-derived predicate is placed provisionally on the Input side;
- existing provenance diagnostics remain valid;
- unknown mixed conditions remain explicit and are not silently classified.

## 10. Verification contract

### 10.1 Structural tests

- Priority Exclusion is Guard, not Input Pattern.
- `otherwise` is Guard, not Input Pattern.
- Input-derived function predicates can be Guards.
- Source State selector equality is absent from Guard.
- Multiple alternatives produce multiple Enabling Cases.

### 10.2 Semantic preservation tests

For bounded Boolean examples, enumerate all input assignments and prove:

```text
compiled exact enabling condition
==
Input Pattern AND semantic Guard
```

For fallback, compare against the exact complement stored in the fallback Guard.

### 10.3 Metamorphic tests

Adding an earlier ordered clause MUST change only the later case Guard. It MUST NOT change the later Input Pattern, Action, or Target State.

Renaming Input, Guard predicate, Action, or Target State MUST affect only the corresponding role.

### 10.4 Browser contract

Motor Safety MUST expose:

```text
fault=true                          ➞ LatchFault
emergency=true [fault=false]        ➞ EmergencyBrake
enabled=false [fault=false & emergency=false] ➞ DisableMotor
[otherwise]                         ➞ SetMotorPower(...)
```

A DOM value such as `input.emergency&!input.fault` in `data-input-value` is a test failure.

### 10.5 Snapshot contract

IR and DOM semantic checks run before PNG comparison. PNG is secondary evidence only.

## 11. Non-goals

- no new Glyph syntax;
- no unrestricted natural-language inference;
- no unbounded symbolic execution;
- no classification based only on identifier names;
- no requirement that every machine have an explicit event sum type.

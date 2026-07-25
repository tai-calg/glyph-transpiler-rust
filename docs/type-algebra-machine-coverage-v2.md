# Type Algebra Machine Coverage v2

## Status

Design baseline for PR #25. This work remains on `agent/type-algebra-tooling`; the PR stays Draft and must not be merged without an explicit instruction.

## Problem

The first coverage implementation computes:

```text
|entire state product| × |all input values|
```

This is mathematically valid as a value-space size, but it is not the transition table that a Glyph `machine` actually dispatches over. A machine declares one selector:

```glyph
machine Controller(state:System,input:Input)
  select=state.mode
```

The operational transition domain is therefore the selector variant and the finite input domain. Counters, buffers, timestamps, and other non-selector fields must not multiply the number of transition rows unless a guard actually observes them.

## Goal

For every machine whose selector and inputs can be finitely enumerated within a configured bound, compute an ordered-guard coverage matrix over:

```text
selector variant × input values
```

Classify each concrete row as one of:

- `defined`: an explicit non-default guard is the first matching branch and returns a state value
- `rejected`: the first matching branch explicitly returns `Err(...)`
- `fallthrough`: the default (`_`) branch is selected
- `missing`: every supported guard is false and no default branch exists
- `unknown`: at least one guard needed to decide the row uses an unsupported or non-enumerated value

Also report:

- `overlap`: more than one explicit guard is true for the same concrete row; source order selects the first
- `unreachable`: a guard is never the first matching branch for any concrete row
- `unsatisfiable`: a guard is false for every concrete row
- `shadowed`: a guard is true for at least one row but always preceded by another true guard

## Non-goals

- Proving arbitrary user functions, external effects, floating-point predicates, or recursive domains
- Treating `unknown` as `missing`
- Enumerating the complete value space of non-selector state fields
- Inferring business meaning from names
- Changing machine execution semantics
- Changing existing Public IR schemas in place

## Exactness boundary

Coverage is exact only when all of the following hold:

1. The selector is a declared sum type.
2. Selector states are represented by its variants.
3. Every machine input has a finite structural domain that can be enumerated within the coverage limit.
4. Every guard required to select a branch can be evaluated by the supported pure expression subset.
5. The next function is directly identifiable from the machine declaration.

When a condition depends on an unenumerated state field, an unknown function call, a recursive value, or another unsupported operation, affected rows become `unknown`. The analyzer must not emit a false `missing` warning.

## Finite value model

The analyzer uses a semantic value model rather than parsing generated Rust strings.

Supported domains:

- `bool`
- unit `()`
- nullary and payload sum variants
- product types
- tuples
- `Option<T>`
- `Result<T,E>`
- aliases of supported domains

Integer types remain cardinality-known but are not exhaustively enumerated by default. This prevents accidental expansion of `u8` or larger domains.

Every value retains:

- declared type
- canonical identity
- display text
- optional scalar
- optional variant
- named or positional children

## Guard evaluator

The evaluator is deterministic and three-valued:

```text
true | false | unknown
```

Supported expressions:

- boolean and numeric literals
- parameter names
- product field selection
- selector field selection
- nullary variant constants when unambiguous in context
- `==`, `!=`
- `&`, `|`, unary `!`
- numeric `<`, `<=`, `>`, `>=`, `+`, `-`, `*`, `/` when both operands are known scalars

Function calls and effectful constructs are `unknown`, except that result constructors are inspected when classifying the selected branch value.

Three-valued boolean operations use conservative short-circuit rules:

```text
false & unknown = false
true  & unknown = unknown
true  | unknown = true
false | unknown = unknown
```

## Ordered guard semantics

Glyph guards are ordered. For one concrete domain row:

1. Evaluate explicit guards in source order.
2. The first `true` guard is selected.
3. A default clause is selected only after every preceding explicit guard is false.
4. If no clause is selected:
   - `missing` when all evaluated guards are false
   - `unknown` when selection depends on an unknown result
5. Count all explicit guards that evaluate true. More than one produces an `overlap` witness even though runtime behavior remains deterministic by source order.

## Branch classification

The selected clause value is classified structurally:

- `Err(...)` → `rejected`
- default clause → `fallthrough`
- any other selected expression → `defined`

The analyzer also attempts to determine the target selector variant from direct state construction, `Ok(state construction)`, or returning the current state. Failure to determine a target does not invalidate branch coverage; target state is recorded as unknown.

## IR

`MachineCoverage` remains backward compatible at the field-name level, but `state_cardinality` is redefined as the selector-state cardinality and accompanied by explicit metadata:

```text
domain_semantics = selector×input
selector_field
selector_type
selector_cardinality
input_cardinality
possible_pairs
defined_pairs
rejected_pairs
fallthrough_pairs
missing_pairs
overlap_pairs
unknown_pairs
complete
exact
cases[]
guards[]
```

`complete` means no `missing` and no `unknown` rows. `overlap` does not make the table incomplete, but it emits a warning because behavior depends on clause order.

## Diagnostics

The tooling layer emits warnings with concrete witnesses:

- `machine-coverage-missing`
- `machine-coverage-overlap`
- `machine-coverage-unreachable`
- `machine-coverage-unknown`

Warnings include the machine name, source line, counts, and a bounded set of selector/input examples.

## Artifacts and Studio

The normal compiler artifact set and Glyph Studio both expose:

```text
type-algebra-tooling.json
```

The Type Algebra Studio view shows:

- selector and input domain sizes
- outcome counts
- coverage completeness
- case matrix
- overlap/missing/unknown witnesses
- per-guard reachability

The original seven Glyph 0.4 orthogonal semantic views remain unchanged.

## Safety invariants

1. Unsupported conditions never become `false` by default.
2. Unknown rows never become missing rows.
3. Source order is preserved exactly.
4. Default clauses do not count as overlaps.
5. Coverage generation cannot change generated program behavior.
6. Enumeration is bounded before materializing the Cartesian product.
7. Existing type algebra and Studio Public IR contracts remain compatible.

## Delivery stages

### Stage A — semantic finite values

- Add bounded structural value enumeration.
- Add typed field lookup and canonical equality.

### Stage B — ordered guard matrix

- Resolve selector, next function, and finite inputs.
- Evaluate each concrete row.
- Compute outcomes, overlaps, and guard reachability.

### Stage C — diagnostics and artifacts

- Add machine coverage diagnostics.
- Generate `type-algebra-tooling.json` from the normal compilation path.
- Project the matrix into Studio.

### Stage D — executable witnesses

Generate Rust tests only when the compiler can construct every required state and input witness without inventing values for unobserved fields. This stage is deliberately separate; a misleading fabricated state is worse than no generated test.

# Machine Coverage Symbolic Partitions

## Status

Design extension for PR #25 on `agent/type-algebra-tooling`. The pull request remains Draft and must not be merged without an explicit instruction.

## Problem

The original coverage analyzer materializes every value in:

```text
selector variant × input values
```

This is appropriate for small algebraic domains, but it fails for otherwise analyzable machines such as:

```glyph
>step(state:State,value:u64):State|Error
  value<10 >> Err(TooSmall)
  value==100 >> Ok(State(Ready))
  _ >> Ok(state)
```

The concrete domain contains `2^64` values, while the guards distinguish only four behaviorally different regions:

```text
0..=9
10..=99
100
101..=u64::MAX
```

Raising the enumeration limit is not a valid solution. It only postpones the same failure and can exhaust memory.

## Goal

Preserve exact coverage counts and reachability results without enumerating every concrete input value.

The analyzer uses two execution modes:

1. exact concrete enumeration for small domains;
2. guard-driven symbolic partitioning when concrete enumeration is unavailable or the Cartesian product exceeds the normal coverage limit.

No Glyph surface syntax is added or changed.

## Abstract region

A symbolic region contains:

```text
representative concrete value
exact cardinality
human-readable region description
```

Example:

```text
representative = 10
cardinality    = 90
region         = 10..=99
```

The representative is used to evaluate the existing guard AST and to generate one executable Rust witness. The cardinality is used to compute exact concrete-case counts.

## Integer domains

Supported integral types:

```text
U, I
usize, isize
u8, i8
u16, i16
u32, i32
u64, i64
u128, i128
```

Type aliases resolving to these types are also supported.

For each integral input path, the analyzer collects literal comparison boundaries from guards:

```text
==  !=  <  <=  >  >=
```

Boundary construction:

```text
x < c   or x >= c  -> split at c
x <= c  or x > c   -> split at c + 1
x == c  or x != c  -> split at c and c + 1
```

All boundaries are clamped to the integral type's legal minimum and maximum.

Each resulting interval is behaviorally uniform for supported comparisons, so evaluating one representative is exact for the whole interval.

## Large finite algebraic domains

The same partition mechanism compresses finite product and sum domains.

### Unobserved fields

A field not referenced by any guard is represented by one region whose cardinality equals the field's complete value count.

Example:

```glyph
*Input(active:bool,a:bool,b:bool,c:bool,d:bool)

>step(state:State,input:Input):State
  input.active==true >> State(Running)
  _ >> state
```

Only `active` affects branch selection. The remaining four booleans are grouped into a region of cardinality `16` instead of producing sixteen duplicate rows.

### Sum variants

For a sum value compared against named variants:

- explicitly compared variants receive their own region;
- all unmentioned variants are grouped into one `other` region;
- payload cardinalities remain part of the exact region weight.

Grouping is permitted only when the supported guard subset proves that every grouped value has the same branch behavior.

## Product domains

Product input regions are formed from the Cartesian product of field regions, not field values.

```text
concrete cardinality = product of field cardinalities
symbolic regions     = product of field partition counts
```

This allows a product with billions of values to remain a small exact partition when only a few fields are inspected.

## Supported symbolic guard subset

A non-singleton symbolic region is evaluated only for expressions whose truth value is uniform over the region:

- boolean literals;
- boolean input paths;
- unary `!`;
- `&` and `|` over supported predicates;
- path-to-literal comparisons using `==`, `!=`, `<`, `<=`, `>`, `>=`;
- selector-to-variant comparisons;
- integer and boolean field comparisons inside product inputs.

The following are not assumed uniform:

- arithmetic transformations such as `x+1<10`;
- comparisons between two symbolic paths;
- user-function calls;
- external effects;
- recursive or opaque predicates.

Affected regions become `unknown`; they never become false, missing, or unreachable by assumption.

## Ordered guard semantics

Partitioning does not alter source-order behavior.

For each symbolic region:

1. evaluate guards in source order;
2. select the first true guard;
3. select `_` only if all preceding guards are false;
4. classify unsupported selection as `unknown`;
5. multiply outcome and guard counters by the region cardinality.

Consequently, `defined_pairs`, `rejected_pairs`, `fallthrough_pairs`, `missing_pairs`, `overlap_pairs`, and `unknown_pairs` remain concrete-case counts even though the matrix contains fewer symbolic rows.

## Artifact schema extension

Partitioned coverage remains backward compatible with existing fields and adds:

```text
partitioned
region_count
concrete_case_count
```

Each partitioned case adds:

```text
multiplicity
regions[]
```

Example:

```json
{
  "inputs": [{"name": "value", "value": "10"}],
  "regions": [{"name": "value", "value": "10..=99"}],
  "multiplicity": "90",
  "outcome": "fallthrough"
}
```

`inputs` contains executable representative values. `regions` describes the complete represented subset.

### Exact large-count interchange

Existing numeric count fields are retained for compatibility. Because JavaScript numbers cannot exactly represent every integer above `2^53 - 1`, tooling JSON also emits authoritative decimal-string fields:

```text
defined_pairs_exact
rejected_pairs_exact
fallthrough_pairs_exact
missing_pairs_exact
overlap_pairs_exact
unknown_pairs_exact
```

Guard counters likewise emit:

```text
true_cases_exact
first_match_cases_exact
shadowed_cases_exact
unknown_cases_exact
```

Consumers that require exact arithmetic must prefer the `*_exact` field. Glyph Studio parses these strings with `BigInt`; it does not convert them through an IEEE-754 number first.

## Executable Rust witnesses

One Rust witness is generated per deterministic symbolic region, using its representative value.

The witness proves that the generated Rust transition function agrees with the static result at a concrete point in that region. Exact region-wide coverage continues to rely on the compiler's partition proof.

No witness is generated when:

- the region outcome is `missing` or `unknown`;
- the complete state value cannot be constructed safely;
- the next call is not directly executable by the existing witness generator;
- the target selector cannot be matched safely.

## Limits

`coverage_limit` is reinterpreted as a maximum symbolic region count when partitioning is required. It is not a maximum concrete input cardinality.

The default remains:

```text
256 symbolic selector×input regions
```

A separate materialization limit is used only for small fallback domains and selector construction.

If symbolic region count itself exceeds the configured limit, analysis returns `unknown` with the required region count. It does not partially enumerate or silently sample.

## Safety invariants

1. Concrete enumeration remains the preferred path for small domains.
2. Region cardinalities are exact integers.
3. Unsupported symbolic predicates become `unknown`.
4. Unknown regions never become missing or unreachable.
5. Representative values always belong to their displayed region.
6. Source order and default-branch semantics are unchanged.
7. Exact counts are weighted by region cardinality.
8. No input value is fabricated outside its declared type.
9. Exact interchange uses decimal strings beyond JavaScript's safe-integer range.
10. No Glyph syntax or runtime behavior changes.
11. PR #25 remains Draft until explicitly changed.

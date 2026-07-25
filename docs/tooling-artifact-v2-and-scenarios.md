# Tooling Artifact v2 and Multi-step Scenarios

## Status

Design and implementation extension after PR #25. The follow-up pull request remains Draft and must not be merged without an explicit instruction.

## Universal artifact contract

Every successful Glyph compilation emits:

```text
type-algebra-ir.json
type-algebra-tooling.json
type-algebra.generated.rs
machine-coverage.generated.rs
machine-scenarios.generated.rs
```

Sources without machines still emit the artifacts with empty machine arrays and explanatory generated Rust comments. Consumers no longer need to infer whether tooling is available from unrelated Glyph 0.4 features.

## Tooling schema v2

`type-algebra-tooling.json` is normalized to:

```json
{
  "schema": "glyph.type-algebra-tooling",
  "version": 2,
  "diagnostics": [],
  "structural_conversions": [],
  "machine_coverage": [],
  "machine_state_reachability": [],
  "machine_witnesses": [],
  "machine_scenarios": []
}
```

All six arrays are always present. Existing fields inside coverage and witness records remain compatible with the PR #25 representation.

## Multi-step scenario witnesses

A scenario test begins at the exact Rust expression generated from `machine.init` and replays a shortest path over definite successful coverage edges.

For each non-initial `definitely_reachable` selector state, the generator:

1. keeps only `defined` and explicit-default successful cases;
2. requires a structurally known source and target selector;
3. requires direct executable next-call arguments;
4. finds a deterministic shortest path from the initial selector;
5. threads the returned state through every next-function invocation;
6. asserts the selector after every step.

`Result<State, E>` steps explicitly fail the generated test if an unexpected `Err` is returned.

## Exclusions

The generator does not use:

- `rejected`, `missing`, or `unknown` cases;
- possible state-reachability edges;
- successful branches with unknown target selectors;
- payload selector variants that cannot be matched safely;
- next calls whose arguments cannot be represented by existing concrete witnesses.

A skipped target and its reason are recorded in `machine_scenarios`.

## Safety meaning

The generated scenario is an executable witness for one concrete representative path. It validates that the generated Rust transition function agrees with the compiler's definite path analysis at every step. It is not a proof that every input sequence reaches the target.

## Compatibility

- no Glyph surface syntax changes;
- no runtime behavior changes;
- existing small-domain and symbolic coverage semantics remain unchanged;
- Studio and CLI continue to consume the compiler-generated tooling artifact;
- the follow-up PR remains Draft until explicitly changed.

# Type Algebra Tooling Delivery and Executable Witnesses

## Status

Design extension for PR #25 on `agent/type-algebra-tooling`. The PR remains Draft and must not be merged without an explicit instruction.

## Scope

This design completes three internal compiler features without changing Glyph surface syntax:

1. emit `type-algebra-tooling.json` from the normal compilation pipeline;
2. emit executable Rust machine-coverage witness tests when construction is provably safe;
3. emit warnings for guards that cannot be selected for any concrete selector/input case.

## Single artifact source

`build_diagram_bundle()` is the authoritative producer for:

```text
type-algebra-ir.json
type-algebra-tooling.json
type-algebra.generated.rs
machine-coverage.generated.rs
```

CLI, Python APIs, file-based compilation, and Glyph Studio consume the same bundle. Studio may project these artifacts into views, but it must not define a different coverage result.

## Tooling JSON

`type-algebra-tooling.json` contains:

- type-algebra diagnostics;
- structural conversions;
- selector-based machine coverage;
- machine witness generation reports.

Witness reports state, per machine and per concrete coverage case:

- whether a Rust test was generated;
- the generated test name;
- why generation was skipped.

The report does not embed Rust source. Rust remains in `machine-coverage.generated.rs`.

## Reachability warnings

The final `_` clause is an explicit default/else branch. Reaching it is normal program behavior and does not emit a warning.

A warning is emitted only when a guard cannot become the first selected branch for any concrete selector/input case:

```text
machine-coverage-unreachable
```

The unreachable classification distinguishes:

- `unsatisfiable`: the guard is false for every concrete case;
- `shadowed`: the guard is true for one or more cases, but an earlier guard always wins;
- `default`: the final `_` branch is never selected because preceding guards cover every concrete case.

`fallthrough` remains an internal coverage outcome for cases handled by `_`. It is visible in JSON and Studio, remains covered for completeness accounting, and is not a diagnostic by itself.

## Executable witness safety boundary

A witness test is generated only when all of the following are proven:

1. selector and input coverage is exact;
2. the complete state value can be structurally enumerated within the witness limit;
3. every argument passed to the machine `next` function is a direct state value, direct machine input, boolean literal, or numeric literal;
4. ordered branch selection is deterministic for that case;
5. the selected outcome is `defined`, `fallthrough`, or `rejected`;
6. for successful outcomes, the target selector variant is structurally known;
7. the selector variant used in the Rust pattern has no payload;
8. the next function returns `State` or `Result<State, E>`.

A missing or unknown coverage case never receives an executable test. A state with non-enumerable unobserved fields also receives no fabricated witness.

## Generated Rust assertions

For a successful plain-state transition:

```rust
assert!(matches!(
    step(State { mode: Mode::Idle }, Event::Start),
    State { mode: Mode::Running, .. }
));
```

For `Result<State, E>` success:

```rust
assert!(matches!(
    step(State { mode: Mode::Idle }, Event::Start),
    Ok(State { mode: Mode::Running, .. })
));
```

For explicit rejection:

```rust
assert!(matches!(
    step(State { mode: Mode::Running }, Event::Stop),
    Err(_)
));
```

Tests call the generated Rust function itself. They do not merely repeat the static guard evaluator.

## Artifact layout

`machine-coverage.generated.rs` follows the same integration convention as the existing type-algebra artifact:

```rust
use crate::generated::*;

#[cfg(test)]
mod glyph_machine_coverage_witnesses {
    use super::*;
    // generated tests
}
```

If no case is safe to construct, the artifact is still emitted with an explanatory generated comment, and `type-algebra-tooling.json` records the skip reasons.

## Compatibility

- no Glyph syntax changes;
- no runtime behavior changes;
- legacy sources without Glyph 0.4 features retain the legacy artifact set;
- `_` remains a normal explicit default branch;
- fallthrough remains covered and visible, without generating a warning;
- unreachable guards emit `machine-coverage-unreachable`;
- unsupported guards remain `unknown`, never `missing`;
- PR #25 remains Draft.

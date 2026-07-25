# Machine State Reachability

## Status

Design extension for PR #25 on `agent/type-algebra-tooling`. The pull request remains Draft and must not be merged without an explicit instruction.

## Scope

Add an init-based selector-state reachability analysis without changing Glyph surface syntax or machine runtime behavior.

The existing machine coverage analysis answers:

```text
Can this ordered guard clause be selected for any selector × input case?
```

This analysis answers a different question:

```text
Can this selector state be reached from machine.init through machine transitions?
```

## Inputs

The analysis consumes:

- the validated `MachineDecl`;
- the selector sum declaration;
- the selector variant constructed by `machine.init`;
- the concrete or partitioned `MachineCoverage` cases.

It does not re-evaluate guards. Coverage remains the authoritative source for branch selection and transition targets.

## Edge classes

Each coverage case contributes one of the following:

### Definite edge

A `defined` or explicit-default (`fallthrough`) case with a structurally known target selector contributes:

```text
source selector -> target selector
```

Returning the current state therefore contributes a self-loop.

### No edge

- `rejected`: the input is intentionally rejected; state does not advance.
- `missing`: no behavior is defined; the existing missing diagnostic is responsible.

Neither is treated as an unreachable-state error by itself.

### Possible edge

A case contributes conservative possible edges from its source to every selector state when:

- the outcome is `unknown`; or
- the selected successful branch has an unknown target selector.

This over-approximation prevents false unreachable warnings.

If coverage has no usable case matrix, all selector states are considered possibly reachable from the initial state and no unreachable warning is emitted.

## Three-way classification

Reachability is computed twice:

1. over definite edges only;
2. over definite plus possible edges.

States are classified as:

- `definitely_reachable`: reachable using definite edges;
- `maybe_reachable`: reachable only when possible edges are admitted;
- `definitely_unreachable`: unreachable even in the over-approximated graph.

Only `definitely_unreachable` emits:

```text
machine-state-unreachable
```

Unknown transition behavior can therefore reduce diagnostic precision, but cannot create a false unreachable warning.

## Artifact

`type-algebra-tooling.json` adds:

```text
machine_state_reachability[]
```

Each machine record contains:

```text
machine
selector_type
initial_state
states[]
definitely_reachable[]
maybe_reachable[]
definitely_unreachable[]
definite_edges[]
possible_edges[]
exact
reason
line
```

## Studio and CLI

- Glyph Studio projects the already-generated `type-algebra-ir.json` and `type-algebra-tooling.json`; it does not recompute Type Algebra or machine coverage.
- `glyphc`, including `--check` and watch mode, prints tooling warnings to stderr.
- Studio and CLI use the same diagnostics from the compilation artifact.

## Safety invariants

1. Explicit `Err(...)` rejection is normal behavior and does not imply an unreachable state.
2. The explicit `_` clause remains a normal default branch.
3. Possible edges are an over-approximation only; they are never presented as definite transitions.
4. A state warning is emitted only when the state remains unreachable after possible edges are included.
5. Coverage guards are not reinterpreted by the state graph analyzer.
6. No Glyph syntax or generated runtime behavior changes.

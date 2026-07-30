# Relational Transition Abstract Interpretation v2

## Status

RTAI v2 is introduced incrementally. The current implementation is a **shadow evidence stage** and does not replace the existing System Action projection.

The shadow stage exists to establish the safety boundary before implementing TEIR lowering, machine-edge preimage analysis, effect summaries, and fixpoint solving.

## Required correctness properties

RTAI targets two separate guarantees.

### Analysis soundness

Every concrete execution must be represented by the abstract result.

```text
ConcreteExecutions(program, context)
  subset-of
Concretization(Analyze(program, context))
```

The analyzer may return an over-approximation or `unknown`. It must not remove a concrete execution because of an unsupported expression, solver timeout, widening, alias uncertainty, or resource limit.

### Exact projection safety

A System Action may be displayed as exact only when all executions represented by the selected context and machine edge have one identical post-transition effect trace.

```text
DisplayedExactAction(context, edge, trace)
  implies
ConcreteEffectTraces(context, edge) == {trace}
```

## Implemented safety boundary

### Monotonic approximation state

`glyph/transition_analysis/exactness.py` defines:

- `exact`
- `over-approximate`
- `unknown`

An exact value requires explicit proof evidence. Precision-loss causes are retained and propagated by `combine` and `degrade`.

An over-approximate or unknown result cannot become exact through normalization or join.

### Property-scoped proof evidence

Exactness proofs are scoped to one property:

- reachability
- transition-call cardinality
- effect trace
- completion
- lowering
- structural identity

A proof for one property cannot satisfy the exactness requirement of another property. In particular, a concrete reachability witness does not prove effect-trace completeness.

### Execution Evidence v2

Each transition receives an additive `execution_evidence_v2` record containing:

- edge identity
- synthesized-failure status
- context evidence bound to the same edge identity
- reachability status and precondition
- call-cardinality upper bound
- effect-trace alternatives
- completion alternatives
- approximation state and loss causes
- exact-projection checker results

The public version marker is:

```text
transition_execution_evidence_version = 2
```

### Independent exact-action checker

`glyph/transition_analysis/projection.py` operates only on Evidence IR. It has no access to the AST, CFG, solver, Machine relation, or rendered action strings.

Exact projection requires all of the following:

1. proven reachability
2. a concrete witness whose `edge_id` equals the selected context edge
3. reachability-scoped exactness proof
4. exact `at-most-one` call-cardinality evidence
5. exact singleton effect trace
6. exact uniformly normal completion
7. no unknown reason
8. structurally valid EffectTrace events

A missing condition causes rejection.

The projected action is constructed directly from the exact singleton EffectTrace. A separately supplied legacy action or display string is never trusted as semantic evidence.

### Legacy shadow adapter

`glyph/transition_analysis/legacy_shadow.py` converts current execution-context records into Evidence v2 conservatively.

Current `resolved` values are **not** treated as exact proofs. They are marked:

```text
over-approximate(legacy-adapter)
```

Current `unresolved` values are marked:

```text
unknown(legacy-unresolved)
```

An edge without an execution context is also `unknown` unless it is an explicit synthesized-failure edge with no caller continuation.

Therefore the shadow evidence cannot currently authorize an exact System Action projection.

This is intentional. Existing display behavior remains active while the new semantic analyzer is built and compared.

## Trusted computing base

Before RTAI becomes the projection source, the following components must be treated as correctness-critical and independently tested:

- parser and type checker
- AST-to-TEIR lowering
- Machine relation normalization
- expression-to-predicate encoding
- solver integration and UNSAT handling
- effect summaries and write footprints
- abstract-store alias updates
- widening and budget fallback
- evidence serialization
- exact-action checker

## Next implementation stages

### Stage A: concrete TEIR semantics

Implement an independent TEIR interpreter. Do not share abstract transfer functions with the interpreter.

Required outputs per execution:

- selected machine edge
- transition-call sequence
- effect sequence
- completion
- return value
- final store

### Stage B: Machine relation

Normalize ordered first-match Machine branches once into edge specifications containing:

- source predicate
- effective guard
- result expression
- target state
- Machine Actions
- completion

### Stage C: TEIR lowering

Lower function guards and block conditionals into one CFG representation. Prove or test preservation of evaluation order, short-circuit behavior, failure propagation, and resource ownership.

### Stage D: guarded abstract states

Introduce guarded alternatives that retain correlation between:

- path condition
- environment
- store
- machine edge
- transition result
- effect trace
- completion

Do not replace guarded alternatives with an unguarded `Phi` that loses path correlation.

### Stage E: transition preimage analysis

For each abstract alternative and Machine edge, compute:

```text
caller_path_condition
and substituted_source_predicate
and substituted_effective_guard
```

`UNSAT` may prove an edge unreachable only when encoding and solver handling are sound. `SAT` on an over-approximation means only `may-reachable` unless a concrete witness is replayed successfully against the same edge.

### Stage F: effect and store semantics

Effect summaries must include:

- return relation
- read footprint
- write footprint
- store transform
- emitted effect event
- completion relation
- approximation status

Unknown write footprints require conservative havoc. Strong store updates are allowed only for a proven singleton abstract location.

### Stage G: fixpoint and widening

Loops and recursive strongly connected components require monotonic transfer functions and safe widening. Widening must preserve over-approximation and must not collapse repeated traces into a false singleton.

### Stage H: oracle and metamorphic validation

Use three independent layers:

1. AST reference interpreter
2. TEIR concrete interpreter
3. RTAI abstract interpreter

Required relation:

```text
AST result == TEIR concrete result
TEIR concrete result subset-of RTAI result
```

Meaning-preserving transformations must preserve normalized evidence. Meaning-changing transformations such as field permutation, guard negation, and effect-order changes must change evidence when concrete semantics changes.

### Stage I: projection switch

Evidence v2 may become the UI projection source only after:

- concrete-execution inclusion tests pass
- exactness proofs are generated by the new analyzer rather than the legacy adapter
- all exact-action checker conditions are satisfied
- synthesized failure never carries caller-side effects
- unknown and over-approximate results are never labeled resolved

## Current non-goals

The shadow implementation does not yet claim:

- exact machine-edge reachability
- exact transition preimages
- complete effectful helper summaries
- alias-correct abstract store updates
- loop or recursive fixpoints
- solver-backed proof certificates
- replacement of existing System Action projection

These properties must not be inferred from the presence of `execution_evidence_v2`.

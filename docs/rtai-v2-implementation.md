# Relational Transition Abstract Interpretation v2

## Status

RTAI v2 is implemented as a **shadow semantic analysis**. It publishes TEIR,
Machine relations, structural transition preimages and Evidence-compatible safety
metadata. Guarded abstract execution is implemented and tested as an internal
analysis API, but its alternatives are not yet converted into public edge Evidence
and do not replace the active System Action projection.

The current implementation establishes the semantic and validation layers needed
before the UI switch. Unsupported RTAI constructs produce explicit `unknown` or
lowering issues and do not break ordinary Glyph compilation.

## Required correctness properties

### Analysis soundness

Every concrete execution must be represented by the abstract result.

```text
ConcreteExecutions(program, context)
  subset-of
Concretization(Analyze(program, context))
```

Unsupported expressions, missing Effect contracts, alias uncertainty, resource
limits and widening must enlarge the result or produce `unknown`. They must never
remove a concrete execution.

### Exact projection safety

A System Action may be displayed as exact only when all executions represented by
the selected context and Machine edge have one identical post-transition Effect
trace.

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

An exact value requires explicit proof evidence. Precision-loss causes are retained
and propagated by `combine` and `degrade`. An over-approximate or unknown result
cannot become exact through normalization, join or projection.

Proofs are scoped to one property, including:

- structural identity
- lowering
- Machine relation
- transition preimage
- TEIR execution
- reachability
- transition-call cardinality
- Effect trace
- completion

A proof for one property cannot satisfy another property's exactness requirement.
A concrete reachability witness does not prove Effect-trace completeness.

### Execution Evidence v2

Each transition receives an additive `execution_evidence_v2` record containing:

- edge identity
- synthesized-failure status
- context evidence bound to the same edge identity
- reachability status and precondition
- call-cardinality upper bound
- Effect-trace alternatives
- completion alternatives
- approximation state and loss causes
- exact-projection checker results

Current legacy `resolved` values are not treated as exact. They are adapted as:

```text
over-approximate(legacy-adapter)
```

Current `unresolved` values and ordinary edges without an execution context are
adapted as `unknown`. Synthesized-failure edges are represented separately as no
caller continuation.

### Independent exact-action checker

`glyph/transition_analysis/projection.py` operates only on Evidence IR. It has no
access to the AST, CFG, solver, Machine relation or rendered action strings.

Exact projection requires all of the following:

1. proven reachability
2. a concrete witness whose `edge_id` equals the selected edge
3. reachability-scoped exactness proof
4. exact `at-most-one` call-cardinality evidence
5. exact singleton Effect trace
6. exact uniformly normal completion
7. no unknown reason
8. structurally valid EffectTrace events

The projected action is constructed directly from the exact singleton EffectTrace.
A separately supplied legacy action or display string is never trusted as semantic
evidence.

## Implemented semantic analysis

### TEIR

`glyph/transition_analysis/teir.py` defines the Transition Execution IR:

- `Assign`
- `TransitionCall`
- `EffectCall`
- `Jump`
- `Branch`
- `Return`
- `PropagateFailure`
- `BasicBlock`
- `Function`

Function guards and `:=` blocks lower into the same CFG representation.
Function-block pipeline and lambda syntax are not parsed twice. TEIR consumes the
compiler-generated value/final helper ASTs, preserving the existing syntax
lowering as the sole syntax implementation.

The public shadow pipeline uses non-fatal lowering. Unsupported functions are
listed in `lowering_issues`; the existing compiler and UI continue to operate.
The concrete oracle uses strict lowering so unsupported constructs fail tests.

### Source and TEIR concrete interpreters

`glyph/transition_analysis/reference.py` interprets source function control flow and
original function blocks. `glyph/transition_analysis/concrete.py` independently
executes TEIR and records:

- selected Machine edge sequence
- transition arguments and results
- Effect sequence
- completion
- return value

The concrete TEIR interpreter does not reuse the legacy System Action evaluator or
abstract transfer functions.

### MachineRelation

`glyph/transition_analysis/machine_relation.py` normalizes supported ordered
first-match Machine branches once.

For guards `g1`, `g2`, and fallback `_`, effective guards are:

```text
g1
!g1 & g2
!g1 & !g2
```

System analysis consumes these effective guards and does not reinterpret the
original guard list. When branch extraction is unsupported, the relation is
`unknown`; an empty relation is not marked exact.

### Relational transition preimages

`glyph/transition_analysis/preimage.py` substitutes System actual arguments into
normalized Machine edge guards and result expressions.

```text
caller_path_condition
and substituted_effective_guard
```

Constructor order, field access and alias-expanded expression structure are
preserved. Field permutation therefore changes the preimage without a dedicated
field-permutation detector.

The current preimage engine performs exact structural substitution and local
simplification. It proves only conditions that simplify directly to Boolean
constants. It does not yet use SMT to prove general satisfiability or
unsatisfiability.

The shadow bootstrap resolves straight-line block-local aliases before computing
call preimages. Cross-block guarded environments are handled by the abstract
solver, not by this bootstrap convenience projection.

### Structured abstract values

`glyph/transition_analysis/abstract_value.py` preserves:

- parameters
- constants
- field projections
- constructor type and ordered arguments
- pure applications
- Phi alternatives
- top and bottom

Constructor field projection is normalized only when the corresponding constructor
argument is known. Same-root values with different constructor order remain
different.

### Alias-safe abstract store

`glyph/transition_analysis/abstract_store.py` separates variable environments from
mutable locations.

- strong update requires a proven singleton abstract address
- uncertain aliases use weak update
- unknown write footprints use havoc
- storing a top value degrades store exactness
- store joins preserve all possible values

### Effect summaries

`glyph/transition_analysis/effect_summary.py` models:

- parameters and return relation
- read locations
- write operations
- emitted Effect event
- possible completion kinds
- approximation status

An Effect without a verified summary uses a conservative fallback:

- top return value
- unknown write footprint
- store havoc
- normal, failure and unknown completion possibilities

### Guarded abstract execution

`glyph/transition_analysis/abstract_state.py` and
`glyph/transition_analysis/abstract_solver.py` retain correlation between:

- path condition
- abstract and symbolic environments
- store
- selected Machine edge
- transition result
- Effect trace
- completion

Machine transition calls split alternatives by relational edge preimage. Effect
calls apply summaries and split normal/failure continuation when necessary.
Unsupported calls become `unknown` instead of being assumed pure.

Alternatives are deduplicated at CFG points. They are not immediately collapsed
into an unguarded Phi.

### Fixpoint budgets and widening

The worklist solver has explicit budgets for:

- total transfer steps
- alternatives per block
- block iterations
- Phi width

When a limit is reached, alternatives are widened to:

- true path condition
- joined environment and store
- top transition trace
- top Effect trace
- all relevant completion possibilities
- explicit widening/resource-limit cause

The solver therefore terminates without silently dropping loop executions. This is
currently a safety fallback, not a precision-optimized recursive SCC solver.

### Bounded oracles

`glyph/transition_analysis/oracle.py` enumerates finite Bool/Product/Sum domains.
It provides two checks:

```text
AST reference result == TEIR concrete result
```

and

```text
TEIR concrete trace/completion
  is covered by
RTAI abstract trace/completion
```

The second check is a bounded regression oracle, not a proof for arbitrary input
domains. It currently checks selected edge sequences, Effect operation sequences
and completion coverage. Return-value and final-store inclusion remain to be added.

### Shadow publication

Each Machine receives additive `rtai_semantic_bootstrap` data containing:

- supported TEIR functions
- TEIR lowering issues
- normalized Machine relation
- block-local alias-resolved transition calls
- structural edge preimages

`projection_source` remains `false`. Guarded abstract-analysis results remain an
internal API until they can be transformed into property-scoped Evidence without
weakening the exact-action checker.

## Trusted computing base

Before RTAI becomes the active projection source, the following remain
correctness-critical:

- parser and type checker
- existing syntax-to-helper lowering
- helper-AST-to-TEIR lowering
- Machine relation normalization
- expression-to-predicate encoding
- SMT integration and UNSAT handling
- Effect summaries and write footprints
- abstract-store alias updates
- widening and budget fallback
- concrete interpreters and oracle comparison
- Evidence serialization
- exact-action checker

## Remaining implementation work

### SMT predicate solver

Add a typed encoder for the supported Glyph theory and a three-valued result:

```text
UnsatProven
SatModel
Unknown
```

A solver timeout or unsupported theory must never become `UnsatProven`. SAT on an
over-approximation remains may-reachable unless a concrete witness is replayed
against the same edge.

### Interprocedural summaries

Add context-sensitive summaries for:

- pure guarded helpers
- effectful helpers
- recursive pure SCCs
- recursive effectful SCCs

Current unsupported nested calls conservatively become `unknown`.

### Source-level loop and recursive fixpoints

The TEIR worklist has safe loop budgets and widening, but source-level recursive
function summaries and precision-oriented SCC fixpoints are not implemented.

### Complete resource semantics

Extend abstract locations and Effect footprints to all Glyph ownership, borrowing,
allocation and mutation forms. Current store primitives enforce the safety
direction but do not yet model every language resource operation.

### Abstract Evidence generation

Convert guarded abstract alternatives into exact/may/unknown edge Evidence. Exact
status must be issued only when the relevant property-scoped proof exists.

### Evidence-based UI projection

The UI may switch from legacy execution contexts only after:

- bounded and targeted concrete-inclusion tests pass
- SMT UNSAT handling is independently tested
- Effect contracts cover supported external operations
- recursive and loop cases safely terminate
- exact Evidence is generated by RTAI rather than the legacy adapter
- all exact-action checker conditions are satisfied
- synthesized failure never carries caller-side Effects
- unknown and over-approximate results are never labeled resolved

## Current claims and non-claims

The current implementation claims:

- structure-preserving TEIR and Machine relation foundations
- exact structural actual-argument substitution
- independent concrete trace collection
- finite AST/TEIR equivalence regression tests
- finite concrete-to-abstract trace/completion coverage tests
- conservative alias, Effect and budget fallbacks
- no change to active UI semantics

It does not yet claim:

- general exact edge reachability
- SMT-backed UNSAT certificates
- complete interprocedural or recursive analysis
- complete ownership/resource modeling
- return-value and final-store abstract inclusion
- formal proof of concrete-execution inclusion
- replacement of existing System Action projection

These properties must not be inferred from `execution_evidence_v2` or
`rtai_semantic_bootstrap` alone.

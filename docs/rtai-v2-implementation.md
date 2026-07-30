# Relational Transition Abstract Interpretation v2

## Status

RTAI v2 is implemented as a **shadow semantic analysis**. The current branch
contains executable TEIR semantics, normalized Machine relations, typed finite
constraint solving, guarded abstract execution, function and Effect summaries,
Capability-IR ownership replay, bounded soundness oracles, property-scoped
Evidence generation, and an Evidence projection readiness gate.

The active System Action UI remains on the legacy projection. RTAI output is
published in parallel and cannot change the active display action in the normal
compiler pipeline.

Unsupported constructs, unbounded theories, missing Effect contracts, unresolved
recursion, alias uncertainty and analysis budgets become explicit `unknown` or
lowering issues. They do not silently become unreachable or exact.

## Required correctness properties

### Analysis soundness

Every concrete execution must be represented by the abstract result.

```text
ConcreteExecutions(program, context)
  subset-of
Concretization(Analyze(program, context))
```

Unsupported semantics may reduce precision. They must not remove a possible
execution.

### Exact projection safety

A System Action may be displayed as exact only when all executions represented by
the selected System context and Machine edge have one identical post-transition
Effect trace.

```text
DisplayedExactAction(context, edge, trace)
  implies
ConcreteEffectTraces(context, edge) == {trace}
```

## Implemented safety boundary

### Monotonic precision

`glyph/transition_analysis/exactness.py` defines:

- `exact`
- `over-approximate`
- `unknown`

Exact values require explicit proof evidence. Precision-loss causes are retained
through joins and transfer. An over-approximate or unknown result cannot become
exact through normalization, merging or projection.

Proof scopes include:

- structural identity
- lowering
- Machine relation
- transition preimage
- TEIR execution
- function summary
- reachability
- transition-call cardinality
- Effect trace
- completion

Proof kinds distinguish structural facts, lowering equivalence, concrete replay,
finite exhaustive oracle results and solver certificates. A proof for one property
cannot satisfy another property's exactness requirement.

### Execution Evidence v2

The legacy compatibility path still emits additive `execution_evidence_v2` data.
Legacy `resolved` values are not exact proofs; they remain
`over-approximate(legacy-adapter)`. Legacy unresolved values remain `unknown`.

RTAI now also emits a separate native abstract Evidence contract:

```text
rtai_abstract_execution_evidence_v2
```

This native contract is keyed by normalized MachineRelation edges and contains
RTAI-generated reachability, cardinality, Effect-trace and completion evidence.
It remains `projection_source = false`.

### Verified reachability witnesses

`analysis_evidence.py` does not accept an arbitrary dictionary as an exact
reachability witness. `verified_reachability_witness(...)` replays a concrete TEIR
execution and verifies that the requested edge occurs in its transition trace.
Exact reachability evidence uses proof kind `concrete-replay`.

A concrete witness proves existence only. It does not prove Effect-trace
completeness, cardinality or completion uniformity.

### Independent exact-action checker

`projection.py` consumes only Evidence IR. It has no access to ASTs, CFGs, solvers,
Machine relations or rendered legacy strings.

Exact projection requires:

1. proven reachability
2. a same-edge verified witness
3. reachability-scoped exactness proof
4. exact `at-most-one` call-cardinality evidence
5. exact singleton Effect trace
6. exact uniformly normal completion
7. no unknown reason
8. structurally valid Effect events

The projected action is constructed directly from the singleton Effect trace.

## Implemented semantic analysis

### TEIR

`teir.py` represents:

- assignment
- transition call
- Effect call
- jump
- branch
- return
- propagated failure
- basic block
- function

Function guards and `:=` blocks lower into one CFG representation. Pipeline and
lambda syntax are not reparsed by RTAI. TEIR consumes compiler-generated helper
ASTs so syntax lowering remains single-sourced.

The shadow compiler uses non-fatal lowering reports. Strict concrete-oracle paths
fail when unsupported TEIR is encountered.

### Independent concrete interpreters

`reference.py` executes source-level function control flow. `concrete.py`
independently executes TEIR and records:

- selected Machine edge sequence
- transition arguments and results
- Effect sequence
- completion
- return or propagated error value

`stateful_concrete.py` additionally allows concrete Effect handlers to return
store writes. Its result includes `final_store`, enabling real store-inclusion
regression tests.

### MachineRelation

`machine_relation.py` normalizes ordered first-match Machine branches once.
For guards `g1`, `g2` and fallback `_`, the effective guards are:

```text
g1
!g1 & g2
!g1 & !g2
```

When complete branch extraction is unsupported, the relation is not marked exact.

### Relational transition preimages

`preimage.py` computes:

```text
caller_path_condition
and substituted_effective_guard
```

System actual arguments are structurally substituted into Machine formals.
Constructor order, field projection and expression structure are retained.

Each edge now publishes a separate three-valued solver result:

- `UnsatProven`
- `SatModel`
- `Unknown`

Only `UnsatProven` authorizes edge removal. `SatModel` proves existence only.
`Unknown` remains reachable in the abstract result.

### Typed finite constraint backend

`typed_smt.py` is the current typed solver trust boundary. Before solving, it
checks:

- variable types
- product fields
- sum variants
- constructors
- Boolean and numeric operators
- pure function calls
- aliases

The current backend performs exhaustive solving over finite Bool/Product/Sum
domains. It can therefore produce exact finite-domain UNSAT certificates and
concrete SAT models. Recursive, unsupported, over-budget or unbounded numeric
domains produce `Unknown`.

This is not yet a general SMT backend for unbounded arithmetic.

### Structured abstract values and alias-safe store

`abstract_value.py` preserves parameters, constants, field projections,
constructors with ordered arguments, applications, Phi alternatives, top and
bottom.

`abstract_store.py` enforces:

- strong update only for a proven singleton address
- weak update for uncertain aliases
- havoc for unknown write footprints
- monotonic loss of store exactness
- value-preserving store joins

### Effect summaries

`effect_summary.py` models:

- parameter substitution
- return relation
- reads
- typed writes through `EffectWrite`
- emitted Effect event
- completion alternatives
- approximation status

Missing summaries use a conservative top result, unknown footprint, store havoc
and normal/failure/unknown completion alternatives.

`ContextualEffectSummaryRegistry` supports entry-specific verified Effect
summaries. A summary selected for one System entry does not leak to another entry.

### Pure summaries and recursive SCC handling

`function_summary.py` builds a call graph and strongly connected components.
It provides:

- ordered guarded alternatives
- context-sensitive actual-argument instantiation
- exact non-recursive helper inlining
- finite summary fixpoint iteration
- explicit `recursive-summary-limit` degradation

An unresolved recursive SCC is never reported exact. The current recursive path is
a safe fallback rather than a complete relational recursive summary domain.

`SummaryAwareAbstractInterpreter` applies pure summaries and entry-specific Effect
summaries during abstract execution.

### Guarded abstract execution and widening

`abstract_solver.py` retains correlation between:

- path condition
- symbolic and abstract environments
- store
- selected Machine edge
- transition result
- Effect trace
- completion

Alternatives are not immediately collapsed into an unguarded Phi. Explicit
budgets bound total steps, alternatives per block, block iterations and Phi width.
Budget exhaustion widens to top traces, joined state and conservative completion
sets rather than dropping execution paths.

### Ownership and resource replay

`ownership_semantics.py` consumes the compiler's existing `CapabilityModel` and
`CapabilityOperation` IR. It does not parse capability syntax again.

The current replay models:

- move availability
- shared borrow reads
- mutable borrow reads/writes
- capability casts
- move/cast operation sequences
- resource read/write/move footprints
- use-after-move and nonexclusive mutable-borrow violations

Invalid or incomplete Capability IR becomes `unknown`. This layer is not yet a
complete lifetime, place-sensitive alias and allocation semantics for every Glyph
resource construct.

## Validation

### AST/TEIR equivalence

For finite Bool/Product/Sum domains:

```text
AST reference result == TEIR concrete result
```

The comparison includes return/error value, Machine edges, Effects and completion.

### Concrete/abstract inclusion

The bounded RTAI oracle checks:

```text
TEIR concrete execution
  is covered by
RTAI abstract execution
```

Coverage includes:

- transition edge sequence
- Effect operation sequence
- completion
- return or propagated-error value
- final store when a stateful concrete interpreter is supplied

This remains a bounded regression oracle, not a formal proof for arbitrary or
unbounded programs.

## Evidence projection migration

`evidence_projection.py` defines three explicit modes:

- `shadow`
- `prefer-exact`
- `strict-exact`

The normal compiler pipeline uses only `shadow`.

The readiness gate verifies that every relevant context passes the independent
exact-action checker and that exact actions agree across contexts. `prefer-exact`
can publish a candidate without replacing the active display. `strict-exact`
removes legacy fallback for relevant unproven contexts, but is not enabled by the
main pipeline.

StateTransitionIR currently publishes:

- legacy-compatible `execution_evidence_v2`
- `rtai_semantic_bootstrap`
- `rtai_abstract_execution_evidence_v2`
- Evidence projection readiness metadata

None is the active UI projection source.

## Trusted computing base

Before strict Evidence projection becomes active, the following remain
correctness-critical:

- parser and type checker
- syntax-to-helper lowering
- helper-AST-to-TEIR lowering
- Machine relation normalization
- typed predicate encoding
- finite solver or future general solver backend
- Effect summaries and write footprints
- abstract store and ownership replay
- widening and budget fallback
- concrete interpreters and bounded oracles
- Evidence serialization
- exact-action checker
- MachineRelation-to-view-edge specialization

## Remaining implementation work

### General solver backend

The finite typed backend is exact for supported finite domains. A general backend
is still required for unbounded integers, reals and richer theories. Its public
result must remain exactly:

```text
UnsatProven | SatModel | Unknown
```

Timeout, unsupported encoding or backend failure must remain `Unknown`.

### More precise recursive summaries

Recursive SCCs terminate safely but unresolved recursion degrades to unknown.
Precision-oriented recursive pure and effectful summaries remain to be built.

### Complete ownership semantics

Capability-IR replay covers core move/borrow/cast behavior. Remaining work includes
place-sensitive aliases, borrow lifetimes, allocation identity, nested resource
fields and integration of ownership state into every abstract transfer.

### Complete Effect contracts

External Effects without verified summaries remain unknown. Projection migration
requires verified return, completion and write-footprint contracts for the
supported production surface.

### Witness generation and edge specialization

The native shadow Evidence adapter currently publishes MachineRelation-edge
Evidence without automatic concrete witnesses. The pipeline still needs:

- bounded or targeted witness generation
- concrete replay retention
- MachineRelation-edge to rendered view-edge specialization
- synthesized-failure specialization

Until then, native reachable contexts remain `may-reachable` and cannot authorize
exact display.

### Strict UI switch and legacy removal

The active UI may switch only after:

- native RTAI Evidence is bound to rendered edges
- exact contexts possess verified replay witnesses
- every supported Effect has an adequate contract
- targeted concrete-inclusion campaigns pass
- unknown and over-approximate states remain visibly unresolved
- strict mode passes snapshot and application tests without legacy fallback

The legacy System Action analyzer can be deleted only after strict Evidence mode
is the sole semantic source. Deleting it earlier would remove the active behavior
before the replacement is proven ready.

## Current claims and non-claims

The implementation currently claims:

- structure-preserving TEIR and MachineRelation foundations
- typed exact finite-domain `UnsatProven / SatModel / Unknown`
- independent concrete replay witnesses
- context-sensitive pure and Effect summary infrastructure
- safe recursive SCC fallback
- Capability-IR ownership replay
- bounded return and final-store inclusion checks
- property-scoped native abstract Evidence
- Evidence projection readiness auditing
- no change to active UI semantics

It does not yet claim:

- general unbounded SMT completeness
- precise analysis of every recursive program
- complete Glyph lifetime and place semantics
- verified contracts for every external Effect
- automatic exact witnesses for every rendered transition
- formal proof of concrete-execution inclusion
- replacement or deletion of the legacy System Action analyzer

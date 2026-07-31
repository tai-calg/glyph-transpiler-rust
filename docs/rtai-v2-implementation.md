# RTAI v2 implementation status

## Current role

RTAI v2 is an executable semantic analysis for System-entry transition behavior. It lowers Glyph execution into TEIR, interprets it concretely and abstractly, publishes property-scoped Evidence, and projects a System Action only when the Exact checker accepts every required proof scope.

The normal application now selects `strict-exact` for the reviewed public strict v1 catalog. Sources outside that catalog, edited catalog artifacts, incomplete Effect surfaces, and unsupported semantics remain on the compatibility shadow path or produce May/Unknown rather than inheriting reviewed witnesses.

## Implemented semantic core

- TEIR and unified control-flow lowering
- ordered first-match MachineRelation
- concrete source and TEIR interpreters
- stateful concrete Effect replay and final store
- path-partitioned abstract execution
- typed finite Bool/Product/Sum constraint solving
- safe `UnsatProven / SatModel / Unknown` boundary
- alias-aware abstract store, havoc and widening
- context-sensitive function and Effect summaries
- recursive SCC detection with safe Unknown fallback
- Capability-IR ownership replay
- bounded AST/TEIR and concrete/abstract oracles
- property-scoped Evidence for reachability, cardinality, EffectTrace and completion
- rendered-view edge specialization

## Public Effect contracts and witnesses

The public strict v1 catalog is defined in `glyph/transition_analysis/public_effect_contracts.py`.

Each verified Effect contract records:

- exact abstract return relation
- declared failure vocabulary
- external read/write footprint
- reviewed concrete replay handler
- review source and notes

The contract audit begins with source-declared top-level `!Effect` operations. Inbound `ext` inputs and `~` Host-pure functions are not treated as outbound Effects.

Witness generation supports:

- exhaustive finite-domain cases
- reviewed targeted existence cases for unsupported or oversized domains
- entry, edge and completion indexing
- explicit incomplete diagnostics

Targeted cases prove only concrete existence. They do not prove input-space exhaustiveness or trace uniqueness.

## Identity hardening

Strict activation is bound to a reviewed program identity rather than a path alone. The current implementation records:

- exact preprocessed compiler-input SHA-256
- canonical entry-signature digest
- outbound Effect-declaration digest
- MachineRelation digest
- semantic-kernel identifier
- combined program fingerprint

A same-name edited source receives a structured blocker such as `source-content-mismatch` and remains in shadow mode.

Native concrete witnesses are additionally bound to:

- program fingerprint
- relation-edge fingerprint
- Effect-contract digest
- concrete-interpreter version
- typed input digest

Native Exact projection rejects missing, incomplete, cross-program and cross-edge witness bindings.

See `docs/rtai-strict-identity-hardening.md`.

## Fail-closed projection

`strict-exact` sanitizes every transition before Evidence is inspected. It removes stale System-owned compatibility projections while preserving Machine-owned Action information. A native System Action is restored only from accepted exact Evidence.

Readiness is separated into:

- `projection_safe`: strict projection is fail-closed
- `projection_complete`: every expected transition is classified
- `all_edges_exact`: every expected transition is Exact

A May or Unknown transition can therefore remain safe without being described as Exact.

## Semantic Effect event identity

Native EffectTrace events carry ordered semantic identities containing program, relation edge, System/entry context, static event shape, alternative index and dynamic trace position.

Display alias suppression no longer uses equal strings. Machine and System presentations are combined only when their complete event-reference sequences are identical. Repeated equal Effect calls retain distinct dynamic event identities and preserve order and multiplicity.

## UI and campaigns

Implemented:

- Exact / May / Unknown transition status
- strict native browser campaign
- authenticated Desktop strict campaign
- public catalog activation in the normal builder
- structured activation blockers in output JSON
- updated Motor Safety strict-exact README baseline
- legacy analyzer disabled in strict output

## Current guarantees

Within supported, contract-bound, sequential models:

- legacy `resolved` data cannot authorize native Exact projection
- missing or invalid Evidence cannot leave a stale System Action
- a witness from another program or relation edge cannot authorize Exact
- equal display text alone cannot collapse two Effect executions
- unsupported or incomplete analysis remains May or Unknown

This is not a proof that an arbitrary Host implementation or physical device follows the reviewed Effect contract.

## Remaining correctness work

1. replace remaining `repr`-based semantic digest components with a fully versioned typed canonical IR
2. propagate relation-edge fingerprints directly from MachineRelation through rendering rather than relying on source-line specialization as a compatibility bridge
3. add Host implementation identity and contract-conformance artifacts
4. propagate source/program identity through live-edit caches and every Desktop response
5. compare source-AST, TEIR and generated-Rust executions for the supported finite surface
6. audit and version the complete semantic trusted-computing-base file set
7. define exact success/failure Host semantics for any currently excluded failure-capable Effect selected for release
8. remove shadow compatibility and delete legacy analyzer modules after no supported path references them

## Deliberate non-claims

The current implementation does not claim:

- general SMT completeness
- complete recursive relational analysis
- complete place/lifetime/allocation ownership semantics
- automatic witness coverage for every non-finite domain
- Host-binary or hardware conformance
- formal proof that the compiler and both interpreters are bug-free

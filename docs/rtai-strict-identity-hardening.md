# RTAI strict identity hardening

This document records the first implementation stage of the strict-exact correctness hardening.

## Implemented trust boundaries

### Reviewed program identity

A reviewed public strict profile is no longer authorized by path, System name, entry name and Effect names alone. The current compiler input is identified by:

- exact preprocessed compiler-input SHA-256
- canonical entry-signature digest
- outbound Effect-declaration digest
- MachineRelation digest
- semantic-kernel identifier
- combined program fingerprint

The path selects a possible catalog profile. It does not authorize strict mode. An edited file at the same path is rejected with a structured blocker such as `source-content-mismatch` and remains in shadow mode.

### Identity-bound concrete witnesses

Native concrete reachability witnesses now carry:

- program fingerprint
- relation-edge fingerprint
- Effect-contract digest
- concrete-interpreter version
- typed canonical input digest

Native Exact projection rejects missing, incomplete, cross-program and cross-edge witness bindings. Legacy Evidence remains readable only for migration paths and does not receive the native origin marker.

### Complete fail-closed strict projection

Strict projection now sanitizes every transition before Evidence is inspected. Missing Evidence cannot preserve stale legacy System Action fields. Machine-owned Action data is retained.

Readiness is split into three independent statements:

- `projection_safe`: strict projection is fail-closed and no stale fallback survives
- `projection_complete`: every expected transition received a classification
- `all_edges_exact`: every expected transition is Exact

Unknown or May transitions can therefore remain safe without being described as Exact.

### Semantic Effect event identity

Native exact EffectTrace events receive ordered semantic references containing:

- program fingerprint
- relation-edge fingerprint
- System and entry context
- static event-shape digest
- alternative index
- dynamic trace position
- final event-reference digest

Display alias suppression no longer uses equal strings. A Machine Action is treated as a compatibility alias only when its complete invocation sequence matches the exact native EffectTrace event-by-event. Equal repeated calls retain separate identities through their distinct trace positions.

## Required fail-closed behavior

The implementation must continue to satisfy:

```text
identity mismatch          -> shadow or Unknown
missing witness binding    -> no Exact Action
missing transition Evidence -> no legacy fallback
same display text only     -> no deduplication
same Effect twice          -> two ordered events
May or Unknown             -> no fabricated System Action
```

## Implemented adversarial coverage

Tests currently cover:

- exact reviewed artifact activation
- comment-only and guard edits at the same path
- structured activation blockers in normal application JSON
- deterministic component identities
- missing Evidence in the expected transition set
- strict sanitization and idempotence
- missing, incomplete, cross-program and cross-edge witness bindings
- typed distinction between integer and floating-point witness values
- repeated equal Effect calls retaining distinct event IDs
- order and multiplicity differences preventing alias suppression
- Motor Safety Machine/native Action aliasing through shared event IDs

## Remaining hardening stages

This stage does not yet prove the full application correct. Remaining work includes:

1. replace `repr`-based semantic components with a fully versioned canonical typed IR
2. propagate relation-edge fingerprints directly through rendering instead of relying on source-line specialization as a compatibility bridge
3. add Host implementation identity and contract-conformance artifacts
4. propagate source/program identity through live-edit cache and Desktop responses
5. compare source-AST, TEIR and generated-Rust executions for the supported finite surface
6. version and audit the complete semantic trusted-computing-base file set
7. remove the legacy analyzer after no supported path depends on it

The public guarantee remains limited to supported, contract-bound, sequential models. Unsupported or unverified behavior must be reported as May or Unknown.

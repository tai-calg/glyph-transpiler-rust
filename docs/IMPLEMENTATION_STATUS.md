# Glyph 0.4 Implementation Status

## Implemented

- backward-compatible opt-in parsing
- `own` / `share` / `link` / `&` / `&mut` / `as`
- move, borrow, capability conversion, partial-place ledger
- stateful `resource T[State]`
- failure-path resource preservation and symbolic resource identity
- apostrophe Contract namespace and `@{'Name}` application
- World, Protocol, Handler, Law, and Bundle semantics
- World crossing and Region escape validation
- retry, rollback, compensation, fallback validation
- product Law integration with temporal reference and streaming monitors
- conditional public IR and verification-class report
- complete Glyph 0.4 acceptance source and generated-Rust compilation
- machine-readable requirement-to-implementation-to-test compliance manifest
- negative-test evidence requirement for every static rule
- frozen Glyph 0.4 public IR schema/version and resource identity shape tests
- byte-for-byte main compatibility audit for legacy Rust, JSON, diagrams, diagnostics, and exit status
- release metadata and documentation consistency gate
- abstract `glyph.host-requirements` IR
- World-specific opaque representation slots for `own` / `share` / `link`
- semantic Host operations for Capability, Resource, World, Protocol, Handler, and Law
- representation-neutral `host-binding.generated.rs` trait scaffold
- standalone `rustc` verification of the generated Host Binding scaffold
- Glyph Studio projection from the canonical typed design
- Capability, Resource identity/state, World/Region, Protocol sequence, Handler exit, Law/monitor, and Verification-strength views
- `glyph.studio-views` version 2 Studio state and `studio-views.json`
- `glyph.studio-semantic-index` version 1 canonical entity/relation graph
- stable semantic IDs independent of view ordering
- source-line navigation from Glyph 0.4 Studio views
- semantic cross-highlight across orthogonal views
- semantic Inspector with typed incoming and outgoing relations
- selection history with previous/next navigation
- deep links using `view` and `select` URL parameters
- global semantic Command Palette
- local view filtering, resizable editor, theme switching, Preview, Save, and Reload workflow
- preservation of the last successful Studio views and Semantic Index after a compile error

## Host Binding boundary

The compiler now emits:

```text
host-requirements-ir.json
host-binding.generated.rs
```

These artifacts specify which semantic operations a project Host must provide. They do not choose concrete ownership containers, handles, managers, actors, schedulers, transports, timers, transaction engines, monitors, or device APIs.

The same Glyph type may have different representation slots in different Worlds. For example, `share Service @ UiWindow` and `share Service @ WorkerTask` are independent associated types in the generated trait.

The design is documented in `HOST_BINDING_DESIGN.md`.

## Glyph Studio 0.4 boundary

Glyph Studio does not parse Glyph 0.4 independently. It projects the already validated typed design into seven orthogonal views:

```text
Capability
Resource identity/state
World/Region
Protocol sequence
Handler exit graph
Law/monitor
Verification strength
```

The projection is implemented in `glyph/studio_views.py` and exposed through `StudioSnapshot.glyph04_views`, `/api/state`, and `studio-views.json`.

`glyph/studio_semantics.py` builds a closed Studio-only semantic graph from the same validated typed design. It does not modify Compiler Public IR or infer a concrete runtime. Entity IDs normalize Glyph declaration kinds into meaning-level identities, so `function`, `effect`, and `opaque` boundaries share the `function:<name>` namespace.

Protocol events retain their structured control path so choice, parallel, repeat, and sequence structure are not erased. Resource views are grouped by symbolic identity rather than only by type name. Aggregate members use canonical type IDs rather than display indexes.

The orthogonal-view architecture is documented in `STUDIO_04_DESIGN.md`. Semantic identity, relation taxonomy, Inspector, cross-highlight, selection history, deep links, and Command Palette are documented in `STUDIO_SEMANTIC_NAVIGATION.md`. Editing and appearance behavior are documented in `STUDIO_UX.md`.

## Not yet implemented

- lowering normal Glyph logic calls into generated Host Binding trait calls
- a concrete reference Host Binding
- automatic selection of any concrete runtime representation
- executable dispatch, transport, timeout, retry, rollback, compensation, or lifecycle-event runtime
- Studio round-trip editing from diagrams back into Glyph source
- live runtime-event streaming and Law violation replay
- multi-hop semantic path-query UI
- a large-design automatic graph layout engine
- project-wide multi-file semantic navigation

These are intentionally separate from the semantic Host Requirement and Studio projection layers. A future concrete adapter may use local ownership, thread-safe ownership, manager handles, actor IDs, process handles, device handles, or other mechanisms without changing Glyph semantics.

## Stabilization outputs

CI generates:

```text
build/glyph04-stabilization.json
build/glyph04-compatibility.json
```

The stabilization report includes requirement coverage, schema freeze results, deterministic complete-example generation, generated-Rust compilation, generated Host Binding trait compilation, release version consistency, and explicit errors.

The compatibility report executes the main-branch and Glyph 0.4 compilers against the same legacy inputs and compares every generated byte plus invalid-input diagnostics.

Studio regression tests additionally verify:

- unique semantic entity IDs
- closed relation endpoints
- known relation taxonomy
- effect/opaque target normalization
- canonical aggregate-member type IDs
- stable Protocol structured paths without false linear edges
- deterministic projection
- Public IR non-mutation
- unknown verification-subject preservation
- semantic UI controls and JavaScript syntax

The gate definition is documented in `GLYPH04_COMPLIANCE.md`.

## Trusted Host boundaries

- concrete representation of `own`, `share`, and `link`
- access mediation through direct values, managers, actors, registries, or remote handles
- locus dispatch and Region lifecycle
- Protocol transport
- timer and cancellation mechanism
- physical resource release
- actual rollback and compensation effects
- business-level idempotency
- runtime Law event delivery

## Not part of Glyph 0.4

- CPU-core affinity and scheduler priority
- physical memory/NUMA placement
- authentication and authorization
- database isolation
- distributed replication/quorum consistency
- general deadlock freedom
- quantitative performance guarantees

## Pull-request policy

PR #10 remains Draft and unmerged until explicit user instruction.

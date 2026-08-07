# Machine Assembly v1

## Purpose

`assembly` names Machine instances and connects an existing `!` operation from one
instance to an existing input parameter of another instance.

```glyph
assembly DoorControl
  door=Door
  safety=Safety
  motor=Motor

  door.notify_safety -> safety.input
  safety.request_motor -> motor.input
```

No Machine-body keyword is added. `raise`, `emit`, `signal`, `queue`, and
`schedule` are not part of v1.

## Meaning of `!`

An operation is resolved per Machine instance.

- connected by the containing Assembly: internal immediate route
- not connected: ordinary Host-facing external operation

A connected operation is one-way in v1:

```glyph
!notify_safety(event:SafetyInput):()
```

Its single argument is the routed payload and its result is unit. It must be a
declaration without a Host prototype body. An unconnected operation retains its
normal request/result contract with the Host.

## Immediate delivery

Delivery occurs at the connected `!` invocation point. The source reaction is
suspended, the target Machine reaction runs to completion, and execution returns
to the source immediately after that invocation. There is no implicit queue or
whole-Assembly synchronous cycle.

Only Machines reached through a route react.

## State and failure semantics

Each instance owns one local state. The reference runtime evaluates a complete
causal reaction against a deep-cloned working state and commits the complete state
configuration only when the top-level reaction succeeds.

- route, re-entry, type, handler, or Host failure discards the working state
- mutable state returned by `states` is a detached snapshot
- routed payloads and Host arguments use copy-by-value semantics
- Host argument audit records are snapshotted before the Host callback runs
- already executed Host effects remain externally observable and cannot be rolled back
- generators are explicitly closed on success and failure so cleanup blocks run deterministically
- when a top-level reaction is active, competing calls are rejected immediately rather than queued or blocked
- same-thread and cross-thread Host-callback re-entry into the same Runtime is rejected

Fail-fast rejection prevents both lost updates and the cross-thread deadlock where
a Host callback waits for a worker that is itself waiting for the active reaction.

A custom `state_cloner` may replace `deepcopy`; it must preserve the Assembly state
mapping and provide true isolation.

## Runtime type and policy contract

Machine Assembly IR version 2 contains immutable structured type references,
product/sum/alias definitions, Machine state and input types, and effect
signatures. The reference runtime validates:

- IR schema and version
- immediate delivery, atomic commit, and non-reentrant policy identifiers
- every initial state
- every external and routed input
- every effect argument
- every Host result
- every returned next state
- signed and unsigned fixed-width integer ranges
- finite floating-point values and the maximum magnitude of `f32` and `f64`

Generic `I`, `Int`, and `Integer` remain unbounded Python integers in the reference
runtime. Fixed-width names such as `u8` and `i32` enforce their declared ranges.
`f32` and `f64` reject NaN, infinity, and out-of-range finite values.

Unknown future IR versions or delivery policies are rejected instead of being
silently interpreted with v1 immediate semantics.

Runtime values use these reference representations:

- nullary sum variant: `"Variant"`
- tuple sum variant: `("Variant", value, ...)`
- record sum variant: `{"$variant": "Variant", ...}`
- product: mapping with exactly the declared fields
- unit: `None`
- `Option<T>`: `None`, `("Some", value)`, or a directly validated value
- `Result<T,E>`: `("Ok", value)` or `("Err", error)`

## v1 restrictions

- one source `instance.effect` has at most one target
- an internal route operation has one payload argument and unit result
- a route target Machine has exactly one non-state input parameter
- a direct route back to the same instance is rejected
- runtime re-entry into an already reacting instance is rejected
- concurrent top-level reactions against one Runtime are rejected rather than serialized
- the source operation must be reachable from a normalized transition Action
- guard-only and state-unreachable operations cannot be routed
- an explicitly empty normalized reachability result is not replaced by syntax-only fallback
- nested helper guard functions absent from the root normalized IR retain their own ordered branch semantics
- nested helper guard functions are traversed only from reachable result expressions
- payload and target input types must match after alias and short-name normalization
- route cycles are diagnosed because an activated cycle causes re-entry failure

Fan-out, queued delivery, synchronized groups, dynamic instances, reentrant
reactions, and instance-aware Rust lowering are deferred.

## IR and tooling

Validated declarations produce immutable `glyph.machine-assembly-ir` version 2.
Nested records use a tuple-backed immutable Mapping with no mutable internal
dictionary or assignable storage. Direct `dict` base-class mutation and attribute
replacement therefore cannot bypass the freeze. `to_dict()` returns a detached
mutable serialization.

Assembly-enabled compilations publish:

```text
machine-assembly-ir.json
machine-assembly.mmd
```

The Assembly set is embedded into typed design JSON under `machine_assemblies`.
Program Identity v2 binds the original source and Assembly topology, so route-only
changes invalidate Evidence and witness caches.

Incremental compilation keys cached outputs by source digest, source name,
source link, and cache schema version. Equal source text compiled from different
locations therefore receives the correct source map and Mermaid links.

## Compiler integration

Assembly-aware parsing, Rust-output blocking, design JSON, and diagram generation
are defined by their owning compiler modules. Package import no longer installs
Assembly support by replacing functions in already imported modules, so behavior
does not depend on import order or module reload timing.

## Rust code generation status

The legacy Rust generator has no Machine-instance identity. Rust output requests
therefore fail before writing files. `--check`, Studio analysis, typed design JSON,
and diagrams remain available and report:

```text
runtime_codegen.status = blocked
runtime_codegen.reason = instance-aware-rust-lowering-not-implemented
runtime_codegen.fail_closed = true
```

## Validation

The final hardening regression set covers tuple-backed IR immutability,
same-thread and cross-thread fail-fast re-entry rejection, fixed-width integer
boundaries, finite floating-point validation, and pre-Host audit snapshots. The
current branch passes CI, Python Test Collection, Public UI SDK, Desktop,
Certified Incremental Layout, and I/O State Diagram Snapshot.

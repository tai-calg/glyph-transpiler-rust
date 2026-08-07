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
- already executed Host effects remain externally observable and cannot be rolled back
- generators are explicitly closed on success and failure so cleanup blocks run deterministically

A custom `state_cloner` may replace `deepcopy`; it must preserve the Assembly state
mapping and provide true isolation.

## Runtime type contract

Machine Assembly IR version 2 contains immutable structured type references,
product/sum/alias definitions, Machine state and input types, and effect
signatures. The reference runtime validates:

- every initial state
- every external and routed input
- every effect argument
- every Host result
- every returned next state

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
- the source operation must be reachable from a normalized transition Action
- guard-only and state-unreachable operations cannot be routed
- nested helper guard functions are traversed from reachable result expressions
- payload and target input types must match after alias and short-name normalization
- route cycles are diagnosed because an activated cycle causes re-entry failure

Fan-out, queued delivery, synchronized groups, dynamic instances, reentrant
reactions, and instance-aware Rust lowering are deferred.

## IR and tooling

Validated declarations produce immutable `glyph.machine-assembly-ir` version 2.
All nested records and sequences are frozen; `to_dict()` returns a detached mutable
serialization.

Assembly-enabled compilations publish:

```text
machine-assembly-ir.json
machine-assembly.mmd
```

The Assembly set is embedded into typed design JSON under `machine_assemblies`.
Program Identity v2 binds the original source and Assembly topology, so route-only
changes invalidate Evidence and witness caches.

## Rust code generation status

The legacy Rust generator has no Machine-instance identity. Rust output requests
therefore fail before writing files. `--check`, Studio analysis, typed design JSON,
and diagrams remain available and report:

```text
runtime_codegen.status = blocked
runtime_codegen.reason = instance-aware-rust-lowering-not-implemented
runtime_codegen.fail_closed = true
```

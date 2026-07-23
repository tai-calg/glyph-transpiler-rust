# Glyph Host Binding Contract

## 1. Purpose

Glyph defines semantic obligations. It must not select a concrete ownership container, scheduler, transport, timer, transaction engine, monitor, or device runtime.

The Host Binding layer answers one question:

> Which semantic operations must a concrete Host provide so that the generated program satisfies the verified Glyph design?

It does not answer:

> Which Rust type or runtime library should implement those operations?

## 2. Three-layer separation

```text
Glyph Semantic Layer
    own / share / link
    Resource identity and state
    World / Region
    Protocol
    Handler
    Law
            ↓
Host Requirement Layer
    opaque representation slots
    required semantic operations
    preconditions and postconditions
    verification boundaries
            ↓
Concrete Host Binding
    Rc / Arc / handle / actor ID
    direct call / executor / process / device
    channel / shared memory / network
    timer / transaction / compensation engine
```

The first two layers are compiler-defined. The third is project-defined.

## 3. Non-commitments

The compiler must never derive any of the following from `share`, `link`, World, Protocol, Handler, or Law alone:

- `Rc`, `Arc`, `Weak`, `Mutex`, `RwLock`
- direct pointer access
- actor or manager architecture
- thread, Tokio task, process, GPU stream, or device queue
- channel type, capacity, overflow policy, or serialization
- wall clock or virtual clock
- database transaction or compensation implementation

Reference adapters may use these mechanisms, but they are examples rather than language semantics.

## 4. Representation slots

A representation slot is an opaque project-specific type required for one semantic value category.

Its identity is derived from:

```text
Capability × Glyph Type × Resource State × World
```

Examples:

```text
own Buffer[Ready] @ WorkerRequest
share Service @ UiWindow
share Service @ WorkerTask
link Context @ AppWorld
```

The same Glyph type may therefore have different Host representations in different Worlds.

```rust
trait GlyphHostBinding {
    type ReprShareServiceUiWindow;
    type ReprShareServiceWorkerTask;
}
```

One may be `Rc<Service>`, another `Arc<Service>`, and another a manager handle. Glyph does not choose.

## 5. Semantic operations

Host requirements are generated only for operations that cross the static/runtime boundary.

### Capability

```text
publish       own → share
clone_share   share → share
downgrade     share → link
clone_link    link → link
resolve_link  link → share | expired
```

`share` means strong liveness, not mutation permission or direct access. `link` never extends liveness.

### Resource

Resource requirements preserve symbolic identity across state transitions and all success/failure exits.

```text
rho:x : own Buffer[Ready]
        ↓
rho:x : own Buffer[Done]
```

The Host may represent `rho:x` as a value, handle, registry key, device allocation, or remote object reference.

### World

A World requirement specifies locus and dynamic Region semantics. It does not specify thread, executor, process, or device mechanics.

### Protocol

A Protocol requirement specifies an ordered trace of send/receive events. It does not specify queue, channel, direct call, shared memory, or network transport.

### Handler

A Handler requirement specifies retry and recovery semantics, including ledger equivalence and identity preservation. It does not specify scheduler, timer, transaction engine, or compensation mechanism.

### Law

A Law requirement specifies canonical runtime events and ordering. It does not specify monitor implementation.

## 6. Host Requirement IR

`host-requirements-ir.json` is versioned as `glyph.host-requirements`, version 1.

```text
representations
    opaque representation slots

operations
    semantic operation ID
    inputs and outputs
    preconditions
    postconditions
    failure possibility
    verification classes

invariants
    global non-commitments and semantic laws
```

This IR is the stable boundary between the compiler and project-specific Host tooling.

## 7. Generated Rust scaffold

`host-binding.generated.rs` is a program-specific trait scaffold.

It contains:

- opaque associated types for representation slots
- one method for each required semantic operation
- precondition and postcondition documentation
- no concrete runtime type or library

The scaffold is intentionally not a complete runtime. A project implements it using its selected architecture.

## 8. Compatibility

Sources that do not use Glyph 0.4 syntax remain on the exact legacy pipeline and do not emit Host Requirement artifacts.

Adding this layer must not change legacy Rust, host stubs, JSON, diagrams, diagnostics, or exit status.

## 9. Acceptance criteria

- The same type can have different representation slots in different Worlds.
- Generated output contains no `Rc`, `Arc`, `Weak`, `Mutex`, Tokio, channel, or CUDA choice.
- Capability conversion preserves semantic identity without prescribing representation.
- Resource transitions preserve symbolic identity.
- World, Protocol, Handler, and Law generate semantic requirements.
- The generated Rust trait compiles standalone.
- Legacy source emits no new artifacts and remains byte-compatible with `main`.

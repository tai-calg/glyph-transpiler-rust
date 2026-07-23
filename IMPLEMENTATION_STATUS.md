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

## Trusted Host boundaries

- concrete Arc/Weak/link implementation
- thread/executor dispatch and Region lifecycle
- transport/channel implementation
- timer/cancellation mechanism
- physical resource release
- actual rollback/compensation effects
- business-level idempotency

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

# Machine Assembly v1

## Purpose

`assembly` names Machine instances and connects an existing `!` operation from
one instance to an existing input parameter of another instance.

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

- connected by the containing Assembly: internal immediate invocation
- not connected: ordinary Host-facing external operation

The two cases retain different result semantics.

### Internal operation

A v1 internal operation has one payload argument and a unit result.

```glyph
!notify_safety(event:SafetyInput):()
```

The argument value is delivered to the target Machine input. The operation return
value is not reused as an event payload. The source reaction resumes with unit
after the target reaction completes.

An internal operation is declaration-only. An inline Host prototype body would
create two competing implementations and is rejected.

### External Host operation

An unconnected operation retains its ordinary request/result contract.

```glyph
!write_motor(command:MotorCommand):Receipt
```

The Host receives the operation arguments and returns a `Receipt`. That result is
returned to the suspended source reaction.

## Immediate delivery

Delivery occurs at the connected `!` invocation point. The source reaction is
suspended there, the target Machine reaction runs to completion, and execution
then returns to the source immediately after that invocation. Operations are not
collected and delivered after the source reaction finishes.

This is causal, depth-first propagation rather than a queue or an implicit
whole-Assembly synchronous step.

```text
Door reaction
  before notify_safety
  notify_safety(EmergencyDetected)
    Safety reaction
      request_motor(StopRequested)
        Motor reaction
          receipt = Host.write_motor(DisableMotor)
  after notify_safety
```

Only Machines reached through an operation route react. Merely belonging to an
Assembly does not cause periodic evaluation or a no-op transition.

## State commit and failure

The reference runtime keeps a working state configuration for the complete
causal reaction.

- nested target states become visible inside the working reaction
- all Machine states commit together when the top-level reaction succeeds
- a route/re-entry/Host failure leaves the prior Machine configuration unchanged
- already executed Host effects cannot be rolled back

Re-entry into an instance already present on the active reaction stack is an
error. This prevents an interrupt-like route from entering the same Machine while
its previous reaction is incomplete.

## v1 restrictions

- one source `instance.effect` has at most one target
- an internal `!` operation has exactly one payload argument
- an internal `!` operation returns `()`
- an internal `!` operation has no inline Host prototype body
- a route target Machine has exactly one non-state input parameter
- the payload argument type equals the target input type after normalization
- a direct route back to the same instance is rejected
- runtime re-entry into an already reacting instance is rejected
- the source operation must be reachable from a transition result/Action path
- an operation used only in a guard predicate cannot be routed
- route cycles are reported because an activated cycle may attempt re-entry

The single-input restriction prevents an immediate route from leaving additional
Machine inputs unspecified. A future input-record or explicit partial-binding
model may relax it without changing the v1 route syntax.

Fan-out, queued delivery, synchronized groups, dynamic instances, internal
request/reply, and reentrant reactions are deferred. They must be explicit future
policies rather than silent reinterpretations of the v1 arrow.

## Compiler model and identity

Assembly-enabled compilation returns an immutable `AssemblyCompilationModel`.
It formally contains:

```text
assemblies
assembly_ir
assembly_source
```

No frozen model is modified with `object.__setattr__`, and module discovery is not
performed through `sys.modules` scanning.

Program Identity hashes both the original Assembly source and a canonical
Assembly topology digest. Changing only a route therefore invalidates Evidence,
witnesses, and semantic caches.

## IR and tooling

Validated declarations produce `glyph.machine-assembly-ir` version 1.

```text
MachineAssemblyIR
  name
  delivery = immediate-call-point
  state_commit = atomic-per-top-level-reaction
  reentrant_reaction = forbidden
  instances[]
    state
    inputs[]
    allowed_effects[]
  routes[]
    source_instance
    source_machine
    effect
    payload_parameter
    payload_type
    result_type = ()
    target_instance
    target_machine
    input
    delivery
    order
```

Assembly-enabled analysis publishes:

```text
machine-assembly-ir.json
machine-assembly.mmd
```

The topology diagram includes Machine inputs, internal routes, and remaining Host
operations. Assembly diagnostics are emitted by CLI tooling as well as stored in
IR.

## Rust code generation status

The current Rust generator has no Machine-instance identity. It cannot lower an
internal route correctly.

The modes are therefore separated:

| Mode | Current behavior |
| --- | --- |
| `--check` | succeeds after Assembly validation |
| diagram/design JSON | succeeds |
| Studio analysis | succeeds with blocked Rust placeholder |
| `compile_source` / `compile_file` | raises `GlyphError` |
| `glyphc -o` | exits nonzero and writes no Rust file |

Design JSON reports:

```text
runtime_codegen.status = blocked
runtime_codegen.reason = instance-aware-rust-lowering-not-implemented
runtime_codegen.fail_closed = true
```

Plain Glyph retains the existing parser, model type, Rust output, and tooling
output unchanged.

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
causal reaction against a type-directed structural clone of the committed state
and commits the complete state configuration only when the top-level reaction
succeeds. Runtime cloning does not invoke Python `deepcopy`/`__deepcopy__` or any
caller-supplied copy protocol.

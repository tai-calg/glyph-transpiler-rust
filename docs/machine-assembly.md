# Machine Assembly v1

## Purpose

`assembly` names Machine instances and connects an existing `!` effect from one
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

An effect is resolved per Machine instance.

- connected by the containing Assembly: internal immediate route
- not connected: ordinary Host-facing external effect

The effect return value is the value delivered to the target input. An internally
routed effect therefore requires an inline body so that its routed value is
defined without requiring a Host implementation for that effect. Any other `!`
effect called by the inline body keeps its own normal Assembly-or-Host resolution.
The compiler requires the routed return type and target input type to match after
alias resolution.

## Immediate delivery

Delivery occurs at the connected `!` invocation point. The source reaction is
suspended there, the target Machine reaction runs to completion, and execution
then returns to the source immediately after that invocation. Effects are not
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
          write_motor(DisableMotor)  # Host effect
  after notify_safety
```

Only Machines reached through an effect route react. Merely belonging to an
Assembly does not cause periodic evaluation or a no-op transition.

## v1 restrictions

- one source `instance.effect` has at most one target
- an internally routed `!` effect has an inline body
- a route target Machine has exactly one non-state input parameter
- a direct route back to the same instance is rejected
- runtime re-entry into an already reacting instance is rejected
- the source effect must be reachable from a normalized transition Action
- an effect used only in a guard predicate cannot be routed
- the effect return type equals the target input type after alias resolution
- route cycles are reported because immediate propagation may attempt re-entry

The single-input restriction prevents an immediate route from leaving additional
Machine inputs unspecified. A future input-record or explicit partial-binding
model may relax it without changing the v1 route syntax.

Fan-out, queued delivery, synchronized groups, dynamic instances, and reentrant
reactions are deferred. They must be explicit future delivery policies rather
than silent reinterpretations of the v1 arrow.

## IR and tooling

Validated declarations produce `glyph.machine-assembly-ir` version 1.

```text
MachineAssemblyIR
  name
  delivery = immediate
  reentrant_reaction = forbidden
  instances[]
  routes[]
    source_instance
    source_machine
    effect
    value_type
    target_instance
    target_machine
    input
    delivery
    order
```

Assembly-enabled compilations also publish:

```text
machine-assembly-ir.json
machine-assembly.mmd
```

The Assembly IR is embedded into the typed design JSON under
`machine_assemblies`. The initial integration attaches `assemblies` and
`assembly_ir` to the existing `CompilationModel` without changing its constructor.
Plain Glyph bypasses the Assembly integration and retains the exact legacy parsing
and tooling paths.

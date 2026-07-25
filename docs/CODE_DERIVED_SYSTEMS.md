# Code-derived systems and explicit external boundaries

## Purpose

A Glyph `system` is a checked projection of executable Glyph structure. It is not a
second, freehand description of the architecture.

The canonical declaration is:

```glyph
system DoorControl=control
```

`control` is the system entry. After the complete file is parsed and validated, the
compiler follows named calls reachable from that function and constructs the system
nodes and edges from those declarations and call sites.

```text
Glyph declarations and expressions
  -> symbol resolution
  -> entry-function call traversal
  -> checked system graph
  -> ArchitectureIR
  -> I/O topology
```

## Why the previous form was rejected

The earlier form allowed undeclared names to create diagram nodes:

```glyph
system DoorControl
  panel -> decide
  sensor -> decide
  decide -> lock
```

`panel`, `sensor`, and `decide` could be absent from the rest of the source. The
renderer silently displayed them as external components with unknown ports. The
result looked executable but was only unrelated diagram metadata.

This is no longer permitted. A system node must resolve to one of:

- a body-bearing Glyph function declared with `>`;
- an explicit external boundary declared with `ext`;
- an effect boundary declared with `!`;
- a pure Rust implementation contract declared with `~` after compiler relabeling.

Types and variants are not callable system nodes.

## Canonical example

```glyph
system DoorControl=control

*PanelInput(open_request:B,authorized:B)
*SensorInput(obstruction:B)
*Input(open_request:B,authorized:B,obstruction:B)
+DoorMode=Closed|Opening|Open|Closing|Alarm
*DoorState(mode:DoorMode)

ext panel():PanelInput
ext sensor():SensorInput
ext actuator(state:DoorState):()

>combine(panel_input:PanelInput,sensor_input:SensorInput):Input=
  Input(
    panel_input.open_request,
    panel_input.authorized,
    sensor_input.obstruction
  )

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request&input.authorized >> DoorState(Opening)
  state.mode==Opening&input.obstruction >> DoorState(Alarm)
  state.mode==Opening >> DoorState(Open)
  _ >> state

>control(state:DoorState):()=
  actuator(step(state,combine(panel(),sensor())))
```

The compiler derives:

```text
control -> actuator
control -> step
control -> combine
control -> panel
control -> sensor
```

It also follows calls inside reachable user functions. If `step` calls `decide`, the
graph contains `step -> decide`.

Compiler-generated helpers such as `__glyph_block_*` and `__glyph_lambda_*` are
flattened. They do not appear as architecture components merely because the surface
syntax used `:=` or a pipeline lambda.

## `ext` declaration

Syntax:

```glyph
ext name(parameter:Type,...):ReturnType
```

Examples:

```glyph
ext read_sensor():Input
ext panel():PanelInput
ext database(request:Query):Record|DatabaseError
```

Rules:

1. `ext` has a required typed signature.
2. `ext` has no Glyph body.
3. duplicate names are rejected by ordinary symbol validation.
4. calls lower through the Host boundary; Glyph does not invent an implementation.
5. the I/O and Architecture views classify the component as `external`, not as an
   undeclared placeholder.

`ext` and `!` are both Host-facing contracts but state different design roles:

```text
ext  external component or externally supplied input/service
!    explicit side-effect operation owned by the designed system
~    logically pure contract whose implementation is supplied in Rust
```

The runtime adapter may ultimately bind an `ext` and a `!` through similar Host
mechanisms. Their architecture meaning remains distinct.

## Diagnostics

### Undeclared entry

```glyph
system Broken=missing
>present(x:U):U=x
```

```text
error: system `Broken` entry `missing` is undeclared
```

### Undeclared reachable call

```glyph
system Broken=control
>control(x:U):U=driver(x)
```

```text
error: call `driver` reachable from system `Broken` is undeclared;
declare an external boundary with `ext driver(...):...`
```

### External declaration repair

```glyph
system Fixed=control
ext driver(x:U):U
>control(x:U):U=driver(x)
```

### Entry is not executable Glyph code

```glyph
system Broken=driver
ext driver(x:U):U
```

The compiler rejects this because an external contract has no Glyph body from which
to derive an implementation graph. The system entry must be a `>` function.

## Optional edge assertions

Indented edges remain available as assertions for architecture tests or reviewed
contracts:

```glyph
system DoorControl=control
  control -> sensor
  control -> step
```

They do not add edges. Every endpoint must be declared and every row must match an
actual direct call derived from the entry graph. This is valid only when `control`
really calls both `sensor` and `step`.

The following is an error even though both declarations exist:

```glyph
system Broken=control
  control -> alarm

!alarm():()
>control():()=()
```

No `control -> alarm` call exists in the code.

Legacy `system Name` blocks without an entry are accepted only as checked assertion
sets. A bare system with neither an entry nor assertions is rejected. New source
should use `system Name=entry`.

## I/O view contract

For a declared system the I/O view exposes:

```json
{
  "kind": "code-derived-system",
  "entry": "control",
  "nodes": [],
  "edges": []
}
```

Every node has a declared signature. The renderer no longer creates `EXTERNAL` nodes
with `none / undeclared` ports from unresolved names. Edges are call relationships and
are labeled `calls` rather than the ambiguous `connects`.

When no `system` declaration exists, the existing whole-program call graph remains
the fallback view.

## Scope and non-goals

The system graph currently represents named call dependency, not runtime scheduling.
An edge does not claim:

- that a branch executes on every invocation;
- that two calls run concurrently;
- message transport or process placement;
- temporal order beyond expression semantics;
- a dataflow wire between selected output and input ports.

Those require dedicated IR. The important guarantee here is narrower and strict:
**every displayed system node and edge has a corresponding declared symbol and code
call.**

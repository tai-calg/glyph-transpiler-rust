# Glyph I/O and State Diagram App

## Purpose

`python3 glyph.py <file.glyph>` compiles one Glyph source file and renders two compiler-derived views:

1. I/O topology
2. state transitions

The application does not execute the designed system and does not reproduce application logic in Python or JavaScript.

```text
Glyph source
  -> CompilationModel
  -> ArchitectureIR / Program AST
  -> ExecutionStructureIR
  -> glyph.io-state-views v1
  -> browser renderer
```

## Start

```bash
python3 glyph.py examples/acceptance/motor_safety.glyph
```

The process binds to `127.0.0.1` and opens the browser. Set a fixed port when necessary:

```bash
GLYPH_DIAGRAM_PORT=7860 python3 glyph.py design.glyph
```

Disable automatic browser opening:

```bash
GLYPH_DIAGRAM_NO_BROWSER=1 python3 glyph.py design.glyph
```

## I/O view

When a `system` declaration exists, its component topology is used.

```glyph
system MotorSafety
  sensor -> decide
  decide -> step
  step -> write_motor
```

Each component bound to a Glyph function or effect displays the exact declared signature:

```text
decide
  input  input: Input
  output Command
```

An external component such as `sensor` is displayed as external with undeclared ports. The renderer does not invent its I/O type.

When no `system` declaration exists, the compiler call graph is used as a fallback. Isolated functions are still rendered.

## State-transition view

A state diagram is generated only from a validated `machine` declaration.

```glyph
machine Motor(state:MotorState,input:Input)
  select=state.mode
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted
```

The renderer displays:

- initial state
- every selector variant
- success and failure states
- statically derived transitions
- transition conditions
- `Any state` when the source state cannot be proven from the guard

Immutable `:=` blocks are lowered into compiler helper functions. The view projection traces state constructors through those helpers, so ordinary block-style transition functions remain visible.

If no `machine` declaration exists, the application displays an empty-state explanation and does not infer a state machine from names or types.

## Live editing

- editing triggers a debounced compile preview
- `Compile` runs an immediate preview without saving
- `Save` writes the source file and recompiles
- external file changes are watched and recompiled
- a compile error keeps the last valid diagrams visible
- clicking a node moves the source editor to its declaration line

## Output artifact

A successful compile writes:

```text
.glyph/<source-stem>/io-state-views.json
```

Schema:

```text
schema: glyph.io-state-views
version: 1
```

The JSON model is backend-neutral and contains systems, typed component ports, type declarations, machines, states, and transitions.

## Non-goals

- Gradio form generation
- runtime invocation
- effect execution
- business-semantic inference
- state-machine inference without `machine`
- external component I/O inference

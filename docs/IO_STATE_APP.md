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
  -> normalized StateMachine analysis
  -> glyph.io-state-views v2
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

Before rendering, the compiler-derived transition relation is normalized:

1. the selector variants define the complete state set
2. wildcard source `*` is expanded into one transition per concrete state
3. wildcard target `*` is resolved as a self-transition
4. unreachable ordered-guard branches are removed
5. reachability is computed from the declared initial state
6. generated helper locations are remapped to the original Glyph source lines

The browser therefore never renders `Any state` as if it were a real state.

The renderer displays:

- the initial-state marker
- every selector variant
- success and failure annotations
- concrete state-to-state transitions
- transition conditions
- unreachable states with a dashed outline
- static-analysis warnings with source line links

Current static diagnostics include:

- `unreachable-branch`: a later ordered guard cannot run because earlier guards already cover all variants of a finite sum type
- `unreachable-state`: no transition path exists from the initial state
- `state-independent-transition`: every active branch applies to every selector state
- `no-static-transitions`: no transition relation could be derived without guessing

Immutable `:=` blocks are lowered into compiler helper functions. State analysis traces state constructors through those helpers while presenting only the original Glyph source locations.

If no `machine` declaration exists, the application displays an empty-state explanation and does not infer a state machine from names or types.

## Live editing

- editing triggers a debounced compile preview
- `Compile` runs an immediate preview without saving
- `Save` writes the source file and recompiles
- external file changes are watched and recompiled
- a compile error keeps the last valid diagrams visible
- clicking a node, transition label, or diagnostic moves the source editor to its source line

## Output artifact

A successful compile writes:

```text
.glyph/<source-stem>/io-state-views.json
```

Schema:

```text
schema: glyph.io-state-views
version: 2
```

The JSON model is backend-neutral and contains systems, typed component ports, type declarations, normalized machines, concrete states, transitions, reachability, and diagnostics.

## Non-goals

- Gradio form generation
- runtime invocation
- effect execution
- business-semantic inference
- state-machine inference without `machine`
- external component I/O inference

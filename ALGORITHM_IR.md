# Source-level Algorithm IR

## Purpose

Algorithm IR is the source-level representation behind Glyph Studio's **Logic** view.
It is built from the user's `:=` function blocks before compiler lowering and therefore
never exposes implementation helpers such as `__glyph_block_*` or `__glyph_lambda_*`.

```text
Glyph source
  := immutable binding
  >> ordered branch / variant pattern
  /> pipeline
  |x| lambda
  ~ Rust implementation
  ! effect boundary
        ↓
Algorithm IR
        ├── algorithm-ir.json
        ├── logic.mmd
        └── Studio Logic view
        ↓
compiler lowering / generated Rust
```

The lowered Execution Structure IR remains available as `execution-ir.json` and
`execution.mmd`. It is useful for compiler and call-graph inspection, but it is not the
primary human-facing algorithm view.

## Example

```glyph
>process(c:Command):U|Error
  speed :=
    c==Stop >> 0
    c==Run(n) >> n
    _ >> 0

  checked :=
    speed
    /> validate?

  normalized :=
    checked
    /> |n| min(n,MAX)
    /> optimize

  emitted :=
    normalized
    /> emit

  Ok(emitted)
```

The IR preserves:

- function and binding order
- immutable binding names and inferred types
- branch conditions, values, variant binders, and source lines
- pipeline input and stage order
- lambda source text instead of synthetic function names
- `function`, `rust`, and `effect` stage classification
- input/output types for stages
- `?` propagation and its `Err` exit
- final return expression

## JSON shape

```json
{
  "source_name": "planner.glyph",
  "functions": [
    {
      "name": "process",
      "return_type": "R<u16,Error>",
      "source": {"line": 7, "column": 1},
      "steps": [
        {
          "kind": "binding",
          "name": "speed",
          "type": "u16",
          "value": {
            "kind": "conditional",
            "branches": [
              {
                "condition": "c==Run(n)",
                "value": "n",
                "binders": ["n"],
                "source": {"line": 10, "column": 1}
              }
            ]
          }
        }
      ]
    }
  ]
}
```

## Mermaid view

`logic.mmd` renders each source function as a subgraph.

- binding nodes are merge points for conditional values
- condition blocks use decision and branch nodes
- pipelines preserve left-to-right stage order
- lambdas display `λ parameter → expression`
- `~` stages use the `rust` class
- `!` stages use the `effect` class
- `?` stages have an explicit `Err` terminal edge
- every source-level node links back to its Glyph line

## Studio behavior

The Logic tab reads `algorithm-ir.json` rather than deriving a view from lowered calls.
Selecting a function, binding, branch, stage, or return moves the source editor to the
corresponding line.

The Symbols view also suppresses names beginning with `__glyph_`, because these are
compiler implementation details rather than design symbols.

## Generated files

```text
.glyph/<source-stem>/
├── algorithm-ir.json   # source-level typed algorithm model
├── logic.mmd           # human-facing algorithm diagram
├── execution-ir.json   # lowered execution/call structure
├── execution.mmd       # lowered execution diagram
├── source-map.json     # reverse map to all generated views
└── index.md            # Architecture, Logic, execution, state, and time views
```

## Invariants

1. Algorithm IR is generated only from source-level block metadata.
2. No identifier beginning with `__glyph_` may appear in `algorithm-ir.json` or
   `logic.mmd`.
3. Binding order must equal source order.
4. Pipeline stage order must equal source order.
5. Source lines must point to the original Glyph file, not generated declarations.
6. `~` and `!` must remain distinct even though both are represented as extern-like
   declarations during parts of compilation.
7. The lowered Execution Structure IR remains separate and is not rewritten to imitate
   the source-level view.

## Validation

The automated tests verify:

- branch and variant binder preservation
- binding and stage order
- inferred stage types
- lambda source display
- Rust/effect classification
- explicit Err paths
- source-map entries for `logic.mmd`
- absence of compiler helper names
- Studio source navigation hooks

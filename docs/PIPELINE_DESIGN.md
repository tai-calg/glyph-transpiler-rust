# Glyph `/>` Lambda Pipeline Design

## Purpose

`system` draws the outer software architecture. `/>` draws the ordered logic inside one component.

```glyph
system Door
  sensor -> ctl
  panel -> ctl
  ctl -> lock
  ctl -> log

>ctl(i:In):C|Error=
  i
  /> validate?
  /> |x| x.value
  /> |n| min(n,MAX)
  /> command
```

The first block answers “which responsibilities are connected?”. The second answers “what happens inside `ctl`, and in which order?”.

## Core semantics

`/>` is left-associative.

```glyph
value /> f /> g
```

is lowered to:

```glyph
g(f(value))
```

A fallible stage uses the existing postfix `?`.

```glyph
value /> validate? /> decide
```

is lowered to:

```glyph
decide(validate(value)?)
```

R1 accepts only unary named stages. Partial application such as `/> min(MAX)` is not accepted; write a lambda instead.

```glyph
value /> |x| min(x,MAX)
```

## Lambda syntax

A pipeline lambda is a single-expression, unary, non-capturing pure function.

```glyph
|x| x+1
|x:U| x+1
```

The input type is inferred from the preceding pipeline value. An explicit annotation may be used when inference is unavailable.

```glyph
input /> |x| x.value
```

R1 lowers each lambda to a deterministic internal pure function and then uses the ordinary Glyph parser, typed semantic model, Rust generator, execution IR, and source mapping. Internal names have the form:

```text
__glyph_lambda_L<source-line>_<index>
```

The declaration is assigned back to the source line where the lambda appeared.

## Capture and purity

Compile-time macros and global constructors are not captures.

```glyph
value /> |x| min(x,MAX)
```

An enclosing runtime variable is a capture and is rejected in R1.

```glyph
>run(value:U,limit:U):U=
  value /> |x| min(x,limit)
```

A lambda may not directly or transitively call an effect boundary. Effects remain named `!` components so Architecture and Logic views do not hide external state changes.

## Multiline layout

The recommended formatter form is one stage per line.

```glyph
>run(x:U):U=
  x
  /> inc
  /> |n| n+1
  /> clamp
```

The single-line form is equivalent.

```glyph
>run(x:U):U=x /> inc /> |n| n+1 /> clamp
```

Blank continuation lines are preserved during lowering so existing source line references remain stable.

## Architecture declaration

Architecture uses one connection per line.

```glyph
system Door
  sensor -> ctl
  panel -> ctl
  ctl -> lock
  ctl -> log
```

Binding is automatic by name:

- same-name `>` declaration: `function`
- same-name `!` declaration: `effect`
- same-name type declaration: `data`
- no declaration: `external`

A component that matches multiple declaration kinds is rejected as ambiguous. Unresolved conceptual or external components are allowed.

## Generated views

A source containing `system`, `machine`, `/>`, guards, and `?` temporal constraints produces:

```text
Architecture  system connections
State         machine initial/transitions/success/failure
Logic         named calls, guards, and lowered lambda stages
Time          temporal constraints
Rust          types, pure functions, effect adapters, monitors
```

Generated files include:

```text
architecture.mmd
architecture-ir.json
execution.mmd
execution-ir.json
machine-<name>.mmd
temporal.mmd
source-map.json
index.md
generated.rs
host.generated.rs
typed-ast.json
```

## Current R1 boundary

Implemented:

- one-connection-per-line `system`
- Architecture IR and Mermaid
- Architecture Studio view
- left-associative `/>`
- unary named stages
- `?` propagation stages
- unary non-capturing pure pipeline lambdas
- inferred lambda input and result types for ordinary Glyph expressions
- Rust generation through deterministic synthetic functions

Not implemented in R1:

- capturing closures
- multi-argument pipeline lambdas
- partial application
- standalone lambdas outside a `/>` pipeline
- nested pipelines inside a lambda body
- runtime `eval`

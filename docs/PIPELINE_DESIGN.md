# Glyph `/>` Lambda Pipeline Design

## Purpose

`system Name=entry` selects the executable entry whose real call graph forms the outer software architecture. `/>` expresses ordered value transformation inside one function.

```glyph
system Door=control

ext sensor():In

>ctl(i:In):C|Error=
  i
  /> validate?
  /> |x| x.value
  /> |n| min(n,MAX)
  /> command

!lock(c:C):B
!log(c:C):B

>apply(c:C):B=lock(c)&log(c)
>control():B|Error=apply(ctl(sensor())?)
```

The compiler derives:

```text
control -> apply
control -> ctl
control -> sensor
apply   -> lock
apply   -> log
ctl     -> validate
ctl     -> command
```

There is no independent freehand architecture block. The outer graph and inner pipeline come from the same functions.

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

The declaration is assigned back to the source line where the lambda appeared. Code-derived system traversal flattens these compiler helpers so they do not appear as public architecture components.

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

Canonical syntax:

```glyph
system Door=control
```

`control` must be a body-bearing `>` function. The compiler resolves declarations after parsing the complete source and follows reachable named calls.

External components are explicit:

```glyph
ext sensor():In
ext panel():In
```

Binding rules:

- `>` declaration: `function`
- `ext` declaration: `external`
- `!` declaration: `effect`
- relabeled `~` declaration: `rust`
- type declaration: never a callable system node
- no declaration: compiler error

Optional indented edges are assertions only:

```glyph
system Door=control
  control -> sensor
  control -> ctl
```

They must match actual direct calls. They cannot create a node or edge.

Full semantics: [`CODE_DERIVED_SYSTEMS.md`](CODE_DERIVED_SYSTEMS.md).

## Generated views

A source containing `system`, `machine`, `/>`, guards, and `?` temporal constraints produces:

```text
Architecture  entry-reachable declared calls
State         machine initial/transitions/success/failure
Logic         named calls, guards, and lowered lambda stages
Time          temporal constraints
Rust          types, functions, Host adapters, monitors
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

- entry-bound, code-derived systems
- explicit typed `ext` boundaries
- checked optional architecture assertions
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
- treating system call edges as process placement or physical wiring

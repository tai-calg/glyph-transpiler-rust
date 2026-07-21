# Glyph: expression trees and one-process development environment

This extension adopts the Lisp ideas that fit a statically typed systems DSL without introducing dynamic typing, garbage collection, or runtime `eval`.

## One public command

```bash
python3 glyph.py examples/lisp_core.glyph
```

This launches Glyph Studio. The same process edits the source, watches external changes, compiles Rust, lowers the typed expression tree, interns `SymbolId` values, displays diagrams, and writes artifacts below `.glyph/<source-stem>/`.

The user does not switch between separate compile, watch, diagram, AST, and REPL commands. `glyphc.py` remains only as a low-level interface for CI and external tooling.

## Pure functions as values

Function values use a statically typed Rust function-pointer contract.

```glyph
>inc(x:U):U=x+1
>apply(f:Fn<U,U>,x:U):U=f(x)
>run(x:U):U=apply(inc,x)
```

`Fn<A,R>` is a one-argument function. `Fn<(A,B),R>` is a two-argument function. Only named pure `>` functions and existing `Fn` parameters may be passed. `!` effect boundaries and functions that transitively call an effect boundary are rejected as values.

Generated Rust:

```rust
pub fn apply(f: fn(u16) -> u16, x: u16) -> u16 {
    f(x)
}
```

## Recursion

Direct and mutual recursion are accepted. Glyph records recursion in the semantic model but does not reject recursion whose termination cannot be proven.

```glyph
>sum(n:U):U
  n==0 >> 0
  _ >> n+sum(n-1)

>loop(x:U):U=loop(x)
```

A direct recursive call with an argument shaped like `parameter - constant` is marked `structural`. Other recursive cycles are marked `unchecked`. `unchecked` is descriptive metadata, not an error and not a termination guarantee.

## Expression-oriented typed tree

Every pure function body is represented as a typed expression tree. A guarded function is one `guard` expression containing ordered `branch` expressions and a final `fallback` expression. Names in the semantic tree refer to deterministic `SymbolId` values.

The Studio `AST` and `Symbols` views expose this model directly. The generated `typed-ast.json` contains interned symbols, typed function expression trees, typed `machine` expressions, recursion metadata, and compile-time macro and temporal-spec symbols.

The source parser AST remains immutable. Name resolution and typing lower it into this semantic tree before Rust and visual output are accepted.

## AST macros

Function-like macros use `@name(parameters)=expression`.

```glyph
@twice(f,x)=f(f(x))
>inc(x:U):U=x+1
>run(x:U):U=twice(inc,x)
```

Expansion substitutes expression nodes, not source strings. Arity, recursive macro cycles, and expansion depth are checked. Object-like `@NAME=expression` macros remain available for constants and common expressions.

AST macros run at compile time only. They cannot call a runtime evaluator or replace an effect boundary dynamically.

## Integrated development loop

Glyph Studio provides these views inside one application:

```text
Overview
Machine
Flow
Temporal
Rust
Host
AST
Symbols
Artifacts
```

Saving the source triggers the same content-addressed compilation pipeline used for external file changes.

```text
source changed
    ↓
parse
    ↓
AST macro expansion
    ↓
SymbolId resolution
    ↓
typed expression tree
    ↓
Rust + execution IR + diagrams
    ↓
Studio refresh
```

Output files are replaced atomically and are not rewritten when their contents are unchanged.

## Low-level interface

`glyphc.py` remains available for deterministic CI and scripts, but it is not the normal interactive interface.

```bash
python3 glyphc.py examples/lisp_core.glyph --check
```

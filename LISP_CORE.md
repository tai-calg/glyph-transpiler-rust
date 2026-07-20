# Glyph: expression trees and development loop

This extension adopts the Lisp ideas that fit Glyph without introducing dynamic typing, garbage collection, or runtime `eval`.

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

```bash
python3 glyphc.py examples/lisp_core.glyph \
  --ast-json build/lisp-core/typed-ast.json
```

The JSON contains interned symbols, typed function expression trees, typed `machine` expressions, recursion metadata, and compile-time macro and temporal-spec symbols.

The source parser AST remains immutable. Name resolution and typing lower it into this semantic tree before Rust and development-tool output is accepted.

## AST macros

Function-like macros use `@name(parameters)=expression`.

```glyph
@twice(f,x)=f(f(x))
>inc(x:U):U=x+1
>run(x:U):U=twice(inc,x)
```

Expansion substitutes expression nodes, not source strings. Arity, recursive macro cycles, and expansion depth are checked. Object-like `@NAME=expression` macros remain available for constants and common expressions.

AST macros run at compile time only. They cannot call a runtime evaluator or replace an effect boundary dynamically.

## Development REPL

```bash
python3 glyphc.py examples/lisp_core.glyph --repl
```

Commands:

```text
:check
:symbols
:type NAME
:ast NAME
:diagram
:reload
:help
:quit
```

The REPL evaluates compiler queries against the same semantic model used by normal compilation. It does not execute arbitrary Glyph code at runtime.

## Incremental compilation and live diagrams

```bash
python3 glyphc.py examples/system_controller.glyph \
  -o demo-system/src/generated.rs \
  --host-output demo-system/src/host.generated.rs \
  --ast-json build/system-controller/typed-ast.json \
  --diagram-dir build/system-controller \
  --watch
```

Watch mode hashes the source. Parsing, semantic lowering, Rust generation, typed-AST generation, and Mermaid generation run only when source content changes. Output files are replaced atomically and are not rewritten when their contents are unchanged.

When `--watch` is used without `--diagram-dir`, diagrams are written below `.glyph/<source-stem>/`. The minimum polling interval is 0.1 seconds.

For CI and scripts, one incremental iteration is available:

```bash
python3 glyphc.py examples/lisp_core.glyph \
  --watch-once \
  --ast-json build/lisp-core/typed-ast.json
```

# Glyph enum variant guard patterns

## Purpose

Guard clauses can inspect sum-type variants and their payloads without expanding a full Rust `match` expression in Glyph.

```glyph
+C=Stop|Run(u)

>speed(command:C):u
  command=Run(value)>>value
  command=Stop>>0
  _>>0
```

The feature is limited to guard conditions. Ordinary expression equality keeps its existing meaning.

## Syntax

```text
subject=Variant
subject=Variant(pattern,...)
```

Pattern arguments:

| Glyph | Meaning |
|---|---|
| `_` | Ignore the payload |
| bare name not in the function parameters | Bind the payload to that name |
| existing function parameter | Compare the payload with that parameter |
| field access, literal, call, or other expression | Compare the payload with that expression |

Examples:

```glyph
command=Stop
command=Run(_)
command=Run(speed)
command=Run(expected)
command=Run(system.sequence)
```

In the fourth example, `expected` is a value comparison when it is already a function parameter. In the third example, `speed` is a new branch-local binding when no parameter named `speed` exists.

## Tuple and named-field variants

Tuple variant:

```glyph
+Pair=Both(u,u)

>second(pair:Pair):u
  pair=Both(_,value)>>value
  _>>0
```

Named-field variant declarations continue to use positional pattern arguments in Glyph. The transpiler maps them to Rust field patterns.

```glyph
+Event=Fault{code:u,active:b}|Clear

>fault_code(event:Event):u
  event=Fault(code,_)>>code
  _>>0
```

Generated Rust pattern:

```rust
if let Event::Fault {
    code: __glyph_match,
    active: _,
} = event.clone()
{
    let code = __glyph_match;
    return code;
}
```

## Value matching and ownership

The requested system-transition form is accepted directly:

```glyph
>transition(system:System,command:C):System
  command=Run(system.sequence)>>System(Running,system.sequence+1,command)
  command=Run(speed)>>System(Running,system.sequence+1,Run(speed))
  command=Stop>>System(Stopping,system.sequence+1,Stop)
  _>>system
```

The generated matcher uses a clone of the inspected enum value. This preserves the original `command` so the selected branch can move it into the returned system state.

```rust
if let C::Run(__glyph_match) = command.clone() {
    if __glyph_match == system.sequence {
        return System {
            mode: Mode::Running,
            sequence: system.sequence + 1,
            command,
        };
    }
}
```

Generated sum types already derive `Clone` and `PartialEq`; payload types therefore need to satisfy those Rust trait requirements as before.

## Validation

The transpiler rejects:

- incorrect variant-pattern arity
- duplicate binding names within one pattern
- patterns whose right-hand constructor is not a declared variant are not treated as patterns; they remain ordinary equality expressions

The first implementation intentionally does not support nested variant destructuring or combining a variant pattern with another boolean condition in the same guard. Such conditions should be split into ordered guard clauses or moved into a pure helper function.

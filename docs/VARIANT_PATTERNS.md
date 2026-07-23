# Glyph enum variant guard patterns

## Purpose

Guard clauses can inspect sum-type variants and their payloads without expanding a full Rust `match` expression in Glyph.

```glyph
+C=Stop|Run(U)

>speed(command:C):U
  command==Run(value)>>value
  command==Stop>>0
  _>>0
```

The feature is limited to guard conditions. Ordinary expression equality also uses `==`.

## Syntax

```text
subject==Variant
subject==Variant(pattern,...)
```

A single `=` is reserved for declarations and definitions and is rejected inside expressions.

Pattern arguments:

| Glyph | Meaning |
|---|---|
| `_` | Ignore the payload |
| bare name not in the function parameters | Bind the payload to that name |
| existing function parameter | Compare the payload with that parameter |
| field access, literal, call, or other expression | Compare the payload with that expression |

Examples:

```glyph
command==Stop
command==Run(_)
command==Run(speed)
command==Run(expected)
command==Run(system.sequence)
```

`expected` is a value comparison when it is already a function parameter. `speed` is a new branch-local binding when no parameter named `speed` exists.

## Tuple and named-field variants

Tuple variant:

```glyph
+Pair=Both(U,U)

>second(pair:Pair):U
  pair==Both(_,value)>>value
  _>>0
```

Named-field variant declarations use positional pattern arguments in Glyph. The transpiler maps them to Rust field patterns.

```glyph
+Event=Fault{code:U,active:B}|Clear

>fault_code(event:Event):U
  event==Fault(code,_)>>code
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

```glyph
>transition(system:System,command:C):System
  command==Run(system.sequence)>>System(Running,system.sequence+1,command)
  command==Run(speed)>>System(Running,system.sequence+1,Run(speed))
  command==Stop>>System(Stopping,system.sequence+1,Stop)
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

Generated sum types derive `Clone` and `PartialEq`; payload types need to satisfy those Rust trait requirements.

## Validation

The transpiler rejects:

- single `=` in a guard expression
- incorrect variant-pattern arity
- duplicate binding names within one pattern

A right-hand constructor that is not a declared variant remains an ordinary `==` expression.

Nested variant destructuring and combining a variant pattern with another boolean condition in the same guard are not supported. Split such conditions into ordered guard clauses or move the additional predicate into a pure helper function.

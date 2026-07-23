# Glyph Language 0.4

Glyph is a compact Rust system-design DSL. Glyph 0.4 preserves the existing plain syntax and adds opt-in Capability, Resource, and kinded Contract layers.

## 1. Design principles

1. A symbol has one meaning in a given syntactic position.
2. Plain Glyph remains valid and keeps the legacy Rust generation path.
3. Capability and Resource checks apply only when their syntax is used.
4. Object names and Contract names are lexically distinct.
5. Static guarantees, temporal/runtime monitoring, and trusted Host obligations are reported separately.
6. Concrete threads, executors, transports, timers, Arc/Weak storage, drivers, and physical rollback remain Host responsibilities.
7. `=` defines; `==` compares.
8. Temporal syntax is ASCII and uses `@A` / `@E`.

## 2. Object space and Contract space

Normal identifiers belong to Object space.

```glyph
Image
Failed
process
```

A leading apostrophe refers to Contract space.

```glyph
'ImageWorker
'FailurePolicy
```

The same stem may exist in both spaces.

```glyph
+Failed=Temporary|Permanent
'@Failed=Worker * App/Task
```

```text
Failed     normal type
'Failed    Contract
```

A bare Object name is never implicitly resolved as a Contract.

## 3. Raw expression macros

```glyph
@NAME=expression
```

Example:

```glyph
@LOW=10
@MAX=1000
@BLOCK=s.v<LOW|s.t>80|s.r==0
@LOWER=min

>cap(x:U):U=LOWER(x,MAX)
```

Rules:

- replacement matches complete identifier tokens
- definitions apply to the whole file
- macros may reference other macros
- macros replace expressions, not types or declarations
- duplicate, cyclic, empty, or excessively expanded definitions are rejected
- `A` and `E` are reserved from macro names because `@A` and `@E` are temporal operators

## 4. Plain declarations

### Product type

```glyph
*Point(x,y:F)
```

### Sum type

```glyph
+State=Idle|Run(U)|Fault{code:u8,msg:S}
```

### Type alias

```glyph
=Output=U|Error
```

### Pure function

Single expression:

```glyph
>double(x:U):U=x*2
```

Block expression:

```glyph
>finish(x:I):I
  y := x+1
  y*2
```

The final expression is the return value.

### Guard function

```glyph
>sign(x:I):I
  x<0>>-1
  x==0>>0
  _>>1
```

The fallback `_` clause is explicit and last.

### External effect boundary

```glyph
!send(x:u8):u8|Error
```

A prototype implementation may be attached:

```glyph
!send(x:u8):u8|Error=Ok(x)
```

## 5. Plain types

Long forms:

```text
u8 u16 u32 u64
i8 i16 i32 i64
f32 f64 bool String
R<T,E>  Result<T,E>
O<T>    Option<T>
V<T>    Vec<T>
S       String
```

Short forms:

```text
F -> f32
D -> f64
U -> u16
I -> i32
B -> bool
T|E -> Result<T,E>
```

A product row can be expanded into function parameters.

```glyph
*S(v,t:F,r:U)
>decode(*S):S|Error
```

## 6. Capability types

Capability syntax is opt-in.

```glyph
own T
share T
link T
&T
&mut T
```

| Syntax | Meaning |
|---|---|
| `own T` | unique affine ownership |
| `share T` | explicitly duplicable strong shared ownership |
| `link T` | persistent non-owning link |
| `&T` | temporary read borrow |
| `&mut T` | temporary exclusive write borrow |

Plain `T` is not implicitly `own T`.

### Move

Assignment and by-value calls move affine values.

```glyph
next := owner
```

Using `owner` after this move is rejected.

### Borrow

```glyph
digest := checksum(&buffer)
clear(&mut buffer)
```

Temporary borrows cannot be stored in a binding, field, variant, or return value. `share` and `link` cannot yield `&mut`.

### Capability conversion

`as` changes the capability for the same symbolic object identity.

```glyph
shared := owner as share
copy := &shared as share
weak := &shared as link
other := &weak as link
live := (&weak as share)?
```

Allowed conversions:

```text
own -> share
&share -> share
&share -> link
&link -> link
&link -> share, with failure propagation
```

Rejected conversions include `share -> own`, `own -> link`, Resource state changes through `as`, and general data conversion through `as`.

## 7. Resource types

A Resource declaration defines legal states.

```glyph
resource Buffer[Allocated|Ready|InFlight|Retired]
```

Each Resource use requires both a Capability and a state.

```glyph
own Buffer[Ready]
share Buffer[Ready]
link Buffer[Ready]
```

The following are rejected:

```glyph
Buffer
own Buffer
own Buffer[Missing]
```

Only `own Resource[S]` may transition to another state. The symbolic identity is preserved across the transition.

```glyph
!submit(buffer:own Buffer[Ready]):own Buffer[InFlight]
```

An owned Resource is an obligation. Every control-flow exit must return, transfer, transition, publish, consume, or explicitly recover it.

Failure types must preserve owned Resources.

```glyph
resource Buffer[Ready|Used]
+E=Bad

*WriteError(
  buffer:own Buffer[Ready],
  cause:E
)

!write(
  buffer:own Buffer[Ready]
):own Buffer[Used]|WriteError
```

Aggregate fields are tracked as places such as `pair.left` and `pair.right`, so partial moves remain independent.

## 8. Contract definitions and application

Contract definitions are top-level declarations.

```glyph
'@Name = ...    # World
'>Name = ...    # Protocol
'!Name = ...    # Handler
'?Name = ...    # Law
'Name  = {...}  # Bundle
```

A Contract reference is written as:

```glyph
'Name
```

A Contract is applied to a declaration or supported field position with:

```glyph
@{'Name}
```

Example:

```glyph
'WorkerJob={ 'WorkerTask,'ProcessImage,'FailurePolicy,'Complete30 }

!process(image:own Image[Ready]):ProcessResult
  @{'WorkerJob}
```

`@{WorkerJob}` is rejected because Contract references require the apostrophe.

## 9. World Contract

A World is the product of an execution locus and a dynamic Region path.

```glyph
'@UiWindow=Ui * App/Window
'@WorkerTask=Worker * App/Window/Task
```

World checking covers:

- calls across different loci require a Protocol on the callee
- temporary borrows cannot cross World boundaries
- `own` and `share` values cannot escape from a narrower Region into broader storage
- `link` may be stored beyond the target Region, but Host resolution remains fallible

The Host must implement actual dispatch and Region lifetime closure.

## 10. Protocol Contract

Protocol direction uses explicit arrows.

```text
()          end
-> T        caller sends T to the execution side
<- T        execution side returns T to caller
P >> Q      sequence
P | Q       choice
P || Q      parallel composition
*P          repetition
```

Examples:

```glyph
'>SubmitJob=-> Job
'>RequestReply=-> Request >> <- Response
'>Events=*(<- Event)
'>Duplex=*(-> Command || <- Event)
```

The old shorthand `>T` / `<T` is rejected because it collides visually with function declarations and comparison.

The compiler checks Protocol structure, Bundle conflicts, and compatibility with the applied function signature. Concrete queueing, buffering, ordering, and transport are Host or Law concerns rather than language keywords.

## 11. Handler Contract

Handlers are Contract-library compositions, not a growing list of language keywords.

```glyph
'!RequestPolicy=
  'std.timeout(2s)
  >> 'std.retry(3,'std.exponential,'std.idempotent)
  >> 'std.return_error
```

Standard Contract operations currently recognized:

```text
'std.timeout(Duration)
'std.cancel(...)
'std.retry(Count,Backoff,Idempotency)
'std.rollback(place)
'std.compensate(effect)
'std.fallback(function)
'std.return_error
```

Static checks include:

- retry count is positive
- retry target returns a Result
- retry declares idempotency
- retryable Resource failure paths preserve the entry ledger
- rollback targets an owned Resource
- compensation references an effect boundary
- fallback has a compatible signature
- a Handler has one terminal recovery action

Actual timers, cancellation, business idempotency, rollback, and compensation are trusted Host obligations.

## 12. Law Contract and temporal logic

A Law Contract reuses the temporal formula language.

```glyph
'?Safe=@A(!fault >> stopped)
'?Deadline=@A(start >> @E 2s finish)
```

Product Laws are connected to the existing reference and streaming monitor generation.

```glyph
'Observed={'Safe}
*Observation(fault:B,stopped:B) @{'Observed}
```

Function lifecycle Laws remain in Runtime Contract IR and require Host lifecycle events.

Temporal operators:

```text
!P             not
P & Q          and
P | Q          or
P >> Q         implication
@A P           always
@E P           eventually
@E 500ms P     bounded eventually
P U Q          strong until
P W Q          weak until
```

Composed unary forms:

```glyph
@A@E 1s heartbeat
@E@A stable
```

Bare `A`, `E`, `AE`, and `EA` are not temporal syntax.

## 13. Bundle Contract

A Bundle compresses orthogonal Contracts under one project-level name.

```glyph
'WorkerCall={
  'WorkerTask,
  'RequestReply,
  'RequestPolicy,
  'Deadline
}
```

After expansion:

- at most one World
- at most one Protocol
- at most one Handler
- any number of Laws, combined conjunctively

Handler ordering is written inside the Handler definition, not inferred from Bundle order. Bundle cycles and kind conflicts are rejected.

## 14. Expressions and variant patterns

Expressions include:

```text
name
number
true false
f(x,y)
x.field
expr?
!expr
-expr
a+b a-b a*b a/b
a<b a>b a<=b a>=b a==b a!=b
cond1|cond2
cond1&cond2
```

Variant guard example:

```glyph
+Command=Stop|Run(U)

>transition(system:System,command:Command):System
  command==Run(system.sequence)>>same_speed(system,command)
  command==Run(speed)>>new_speed(system,speed)
  command==Stop>>stop(system)
  _>>system
```

## 15. Built-in constructors and functions

```text
Ok(x)
Err(e)
Some(x)
None
min(a,b)
max(a,b)
finite(x)
```

`Failed`, `GiveUp`, `Retry`, `Stream`, `Latest`, and similar names are not language keywords. They may be normal Object names or apostrophe-prefixed Contract-library names.

## 16. Public IR and guarantee classes

Glyph 0.4 syntax conditionally emits:

```text
capability-ir.json
resource-flow-ir.json
contracts-ir.json
runtime-contract-ir.json
verification-report.json
```

Guarantee classes:

```text
static   compiler proof/check
model    temporal/model analysis
runtime  generated or Host event monitor
trusted  Host adapter or designer proof obligation
```

Sources that do not use Glyph 0.4 syntax do not gain these keys or files.

## 17. Compatibility

No file-level mode is introduced. Existing macros, types, functions, guards, effects, systems, machines, diagrams, and temporal syntax remain valid.

The Glyph 0.4 stabilization gate compares legacy source outputs and diagnostics against `main` byte-for-byte. See `GLYPH04_COMPLIANCE.md`.

## 18. Grammar overview

```text
program              := (macro | declaration | temporal-spec | resource | contract)*
macro                := "@" Name "=" expr
declaration          := product | sum | alias | function | extern
product              := "*" Name "(" compact-fields? ")" contract-application?
sum                  := "+" Name "=" variant ("|" variant)*
alias                := "=" Name "=" compact-type
function             := ">" signature ("=" expr | NEWLINE block) contract-application?
extern               := "!" signature ("=" expr)? contract-application?
resource             := "resource" Name "[" State ("|" State)* "]"
capability-type      := ("own" | "share" | "link" | "&" | "&mut") type
contract-definition  := "'" ("@" | ">" | "!" | "?")? Name "=" contract-body
contract-reference   := "'" Name
contract-application := "@{" contract-reference ("," contract-reference)* "}"
protocol             := "()" | "->" type | "<-" type
                      | protocol ">>" protocol
                      | protocol "|" protocol
                      | protocol "||" protocol
                      | "*" protocol
block                := INDENT (binding | expr)+
binding              := Name ":=" expr
guard                := INDENT (expr | "_") ">>" expr
temporal-spec        := "?" Name "(" temporal-params? ")" "=" formula
formula              := implication
implication          := or-formula (">>" implication)?
or-formula           := and-formula ("|" and-formula)*
and-formula          := until-formula ("&" until-formula)*
until-formula        := unary-formula (("U" | "W") unary-formula)*
unary-formula        := "!" unary-formula
                      | "@A" unary-formula
                      | "@E" duration? unary-formula
                      | "(" formula ")"
                      | atom
```

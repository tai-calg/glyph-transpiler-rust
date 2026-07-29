# Transition Result → Consumer Action Dataflow v1

Status: Implemented

## 1. Problem

A state-transition branch may compute a new state without executing an operation inside the branch itself. The returned value can be consumed later by the caller:

```glyph
>control(state:DoorState):Receipt
  input := combine(panel(),sensor())
  next := step(state,input)
  actuator(next)
```

The semantic Action is `actuator(next)` specialized with the concrete result of each `step` branch. It is not the Target State and it is not a state-carried output value.

## 2. Terms

### Transition Result

The complete value returned by one concrete branch of the machine `next=` function.

### Result Binding

An immutable caller binding whose defining expression directly invokes the machine `next=` function. In the example, `next` is the Result Binding.

### Result-Dependent Operation

An external operation invocation whose argument dataflow contains the Result Binding, including through immutable aliases, product-field projections, and pure helper calls.

### Consumer Action

A Result-Dependent Operation attributed to the transition whose branch produced the consumed Transition Result.

## 3. Required dataflow

```text
machine next branch
  → concrete Transition Result
  → caller Result Binding
  → immutable aliases / product projections / pure helpers
  → external operation invocation
  → transition Action
```

For:

```glyph
next := step(state,input)
actuator(next)
```

and branch:

```glyph
... >> DoorState(Opening)
```

the published Action is:

```text
actuator(DoorState(Opening))
```

For:

```glyph
next := step(state,input)
apply(next)
```

and:

```glyph
>apply(state:DoorState):Receipt|ControlError
  state.action==RaiseAlarm >> alarm(state)
  _ >> lock(state)
```

the compiler specializes the helper against each concrete Transition Result and publishes `alarm(DoorState(...))` or `lock(DoorState(...))` only when the guarded route is provable.

## 4. Invariants

1. Target State never becomes Action.
2. Emitted Output never becomes Action.
3. An unrelated operation after the Result Binding is not an Action unless it consumes the transition result.
4. Immutable aliases preserve result provenance.
5. Pure helper calls may be expanded only while provenance and branch selection remain provable.
6. Multiple caller contexts are accepted only when they produce the same operation sequence.
7. Divergent caller operation sequences produce `STIR_ACTION_RESULT_CONSUMER_AMBIGUOUS`; no Action is invented.
8. An unresolved tainted helper route produces `STIR_ACTION_RESULT_CONSUMER_UNRESOLVED`; the existing Action remains unchanged.
9. Operations executed inside the transition branch remain ordered before downstream Consumer Actions.
10. Renderer code consumes structured `action`; it does not infer Action from names, state values, or label text.

## 5. Caller selection

The compiler finds immutable function blocks containing exactly one direct invocation of the machine `next=` function.

When one or more declared `system entry` functions contain such a binding, only those entry contexts participate. Otherwise, all proven caller contexts participate.

This prevents unrelated helper functions from overriding the declared execution boundary while retaining compatibility for sources without a `system` declaration.

## 6. Published IR

```json
{
  "action": {
    "display": "actuator(DoorState(Opening))",
    "provenance": "transition-operation-invocation"
  },
  "action_invocations": [
    {
      "expression": "actuator(DoorState(Opening))",
      "provenance": "transition-result-consumer",
      "dataflow_path": [
        "step",
        "control.next",
        "actuator"
      ]
    }
  ],
  "action_result_dataflow": {
    "provenance": "transition-result-consumer",
    "caller": "control",
    "binding": "next",
    "path": [
      "step",
      "control.next",
      "actuator"
    ]
  }
}
```

`transition_result_consumer_action_version = 1` identifies this additive contract.

## 7. Acceptance matrix

| Case | Required result |
|---|---|
| Branch-local external invocation | Existing operation-derived Action remains unchanged |
| `step → next → actuator(next)` | Branch-specialized `actuator(TransitionResult)` |
| `step → next → alias → actuator(alias)` | Same specialized Action |
| `step → next → apply(next) → guarded external operation` | Proven guarded operation only |
| `step → next`, followed by unrelated `tick()` | No downstream Action |
| Two callers with identical operation sequences | One unambiguous Action sequence |
| Two callers with different operation sequences | Diagnostic and no invented downstream Action |
| No external operation consumes result | No downstream Action |
| State/output name resembles operation | No lexical inference |

## 8. Completion gate

The implementation is not complete unless all of the following pass:

- compiler IR regression tests;
- exact default-workspace acceptance using `glyph.py::DEFAULT_SOURCE`;
- DoorController helper-routing acceptance;
- negative unrelated-effect and divergent-caller tests;
- browser state-diagram semantic verification;
- SVG/PNG/PDF export regression suites;
- README state-transition snapshot verification.

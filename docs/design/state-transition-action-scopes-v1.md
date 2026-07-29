# State-Transition Action Scopes v1

Status: Implemented

## 1. Problem

A reusable machine transition and the system that executes the machine are different semantic scopes.

```glyph
>step(state:DoorState,input:Input):DoorState
  ... >> DoorState(Opening)

>control(state:DoorState,input:Input):Receipt
  next := step(state,input)
  actuator(next)
```

`step` determines the machine transition. `actuator(next)` belongs to the `control` execution context. Treating the latter as an intrinsic Machine Action makes the same machine impossible to reuse safely from systems with different actuators.

The previous result-consumer pass also recognized only a narrow source shape: a direct immutable binding whose right-hand side was exactly `step(...)`.

## 2. Public semantic axes

Each transition publishes three distinct Action axes.

### 2.1 Intrinsic Machine Action

```json
{
  "machine_action": null,
  "machine_action_invocations": [],
  "machine_effect_invocations": []
}
```

These fields contain only operations proven to execute inside the machine transition result expression.

### 2.2 System execution bindings

```json
{
  "execution_action_bindings": [
    {
      "scope": "system",
      "system": "DoorControl",
      "entry": "control",
      "action": {
        "display": "actuator(DoorState(Opening))"
      },
      "action_invocations": [
        {
          "provenance": "transition-result-consumer"
        }
      ]
    }
  ]
}
```

Every declared `system entry` is analyzed independently. A system operation never mutates `machine_action`.

### 2.3 Display projection

```json
{
  "display_action": {
    "display": "actuator(DoorState(Opening))",
    "provenance": "transition-operation-invocation",
    "projection_provenance": "transition-display-action-projection",
    "scope": "system"
  }
}
```

`display_action` is a rendering projection. Compatibility fields `action`, `action_invocations`, and `effect_invocations` mirror this projection for existing v4 consumers.

The operation provenance remains `transition-operation-invocation`; projection provenance is a separate field and does not replace the semantic origin.

## 3. Composition rules

1. Machine operations are ordered before system result-consumer operations.
2. A single system binding may be selected directly for display.
3. Multiple systems with the same operation sequence may share one display projection while retaining all bindings.
4. Multiple systems with different operation sequences are never collapsed.
5. Divergent systems produce `STIR_SYSTEM_ACTION_CONTEXT_REQUIRED` and require an explicit execution context.
6. A synthesized machine-operation failure has no system result-consumer Action because the machine result was not returned.
7. Target State and Emitted Output remain separate from every Action scope.

## 4. Caller analysis

The execution evaluator recognizes the machine `next=` function through:

```text
direct expression
  actuator(step(state,input))

immutable binding
  next := step(state,input)
  actuator(next)

alias chain
  next := step(state,input)
  forwarded := next
  actuator(forwarded)

pure wrapper
  next := identity(step(state,input))
  actuator(next)
```

The evaluator walks call arguments, immutable definitions, product projections, ordinary expression functions, and ordered guarded pure functions. It substitutes each concrete transition result before publishing an operation expression.

A system entry that invokes the same machine transition function multiple times cannot be represented by one machine edge. It produces `STIR_SYSTEM_ACTION_MULTIPLE_TRANSITION_CALLS` instead of collapsing composed execution into one Action.

An unresolved result-dependent route produces `STIR_SYSTEM_ACTION_UNRESOLVED`; no Action is invented.

## 5. Boolean branch reasoning

After source-state specialization, remaining Boolean expressions are reduced with a bounded reduced ordered binary decision diagram.

The planner therefore proves propositional identities such as:

```text
x | !x  = true
x & !x  = false
```

A true branch exhausts that source state and suppresses later wildcard branches. A false branch is removed. Non-Boolean subexpressions are stable propositional atoms.

Resource bounds are explicit:

- at most 96 atoms;
- at most 50,000 BDD nodes;
- inputs beyond the bound return `unknown` rather than making compilation unbounded.

## 6. IR version ownership

`glyph/state_transition_contract.py` is the sole owner of transition contract versions.

```text
raw normalized machine IR: v2
public StateTransitionIR:   v4
Action scope extension:    v1
result-consumer analysis:  v2
```

The scope fields are additive to public v4. The compatibility `action` projection remains available, so existing v4 readers are not forced to migrate immediately.

Raw and public markers are named separately. Compiler stages import the values from the central contract rather than defining competing schema versions.

## 7. Acceptance requirements

The implementation is incomplete unless all of the following hold:

- `x | !x` exhausts its source before the wildcard;
- `x & !x` is removed before the wildcard;
- direct, bound, aliased, nested, and pure-wrapper result flows are recognized;
- a system Action does not appear in `machine_action`;
- divergent systems remain separate bindings;
- multiple machine calls are diagnosed rather than collapsed;
- synthesized failures do not execute downstream system consumers;
- the exact default workspace still renders concrete `actuator(DoorState(...))` Actions;
- compiler, browser, SVG, PNG, PDF, layout, and snapshot suites pass.

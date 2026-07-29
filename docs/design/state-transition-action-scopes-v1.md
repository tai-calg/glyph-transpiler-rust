# State-Transition Action Scopes v1

Status: Implemented

## 1. Problem

A reusable machine transition and the system that executes the machine are different semantic scopes.

```glyph
>step(state:DoorState,input:Input):DoorState
  ... >> DoorState(Opening)

>control(state:DoorState,input:Input):Receipt
  next := step(state,input)
  record_transition()
  actuator(next)
```

`step` determines the machine transition. Both operations after `step` belong to the `control` execution context:

- `record_transition()` is ordered after the transition but does not consume its result;
- `actuator(next)` consumes the concrete transition result.

Treating either operation as an intrinsic Machine Action makes the same machine impossible to reuse safely from systems with different execution policies. Restricting System Action to result consumers is also incorrect because it drops proven operations that execute after the transition on the same ordered path.

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
        "display": "record_transition(); actuator(DoorState(Opening))"
      },
      "action_invocations": [
        {
          "expression": "record_transition()",
          "provenance": "transition-sequenced-operation",
          "execution_relation": "post-transition-control"
        },
        {
          "expression": "actuator(DoorState(Opening))",
          "provenance": "transition-result-consumer",
          "execution_relation": "result-dependency"
        }
      ],
      "execution_flow": {
        "provenance": "system-transition-execution",
        "result_dependent_count": 1,
        "sequenced_operation_count": 1
      }
    }
  ]
}
```

Every declared `system entry` is analyzed independently. A system operation never mutates `machine_action`.

A System Action is every external operation proven to execute after the single machine transition call on the same ordered execution path. Result dependency is retained as a relation within System Action; it is no longer the admission requirement.

Operations before the transition are preparation or input acquisition and are not attached to the machine edge.

### 2.3 Display projection

```json
{
  "display_action": {
    "display": "record_transition(); actuator(DoorState(Opening))",
    "provenance": "transition-operation-invocation",
    "projection_provenance": "transition-display-action-projection",
    "scope": "system"
  }
}
```

`display_action` is the compiler's automatic rendering projection. Compatibility fields `action`, `action_invocations`, and `effect_invocations` mirror it for existing v4 consumers.

The operation provenance remains `transition-operation-invocation`; projection provenance is a separate field and does not replace the semantic origin.

## 3. Execution ordering contract

For one system entry:

```text
operations before machine transition
  preparation only; excluded from edge Action

single machine transition invocation
  establishes the represented machine edge

operations after machine transition
  included as ordered System Action
```

Composition rules:

1. Machine operations are ordered before system operations.
2. Post-transition system operations retain source execution order.
3. Result-consuming operations use `execution_relation = result-dependency`.
4. Other post-transition operations use `execution_relation = post-transition-control`.
5. A single system binding may be selected directly for display.
6. Multiple systems with the same operation sequence may share the automatic display projection while retaining all bindings.
7. Multiple systems with different operation sequences are never collapsed.
8. Divergent systems produce `STIR_SYSTEM_ACTION_CONTEXT_REQUIRED` and require an explicit execution context.
9. A synthesized machine-operation failure has no downstream success-path System Action because the machine result and normal continuation were not reached.
10. Target State and Emitted Output remain separate from every Action scope.

## 4. Caller and execution-flow analysis

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

ordered post-transition operation
  next := step(state,input)
  record_transition()
  actuator(next)
```

The evaluator walks call arguments in order, immutable definitions, product projections, ordinary expression functions, and ordered guarded pure functions. It substitutes each concrete transition result before publishing result-dependent operation expressions, while retaining result-independent operations that are ordered after the transition.

A system entry that invokes the same machine transition function multiple times cannot be represented by one machine edge. It produces `STIR_SYSTEM_ACTION_MULTIPLE_TRANSITION_CALLS` instead of collapsing composed execution into one Action.

An unresolved post-transition route produces `STIR_SYSTEM_ACTION_UNRESOLVED`; no Action is invented.

## 5. Execution-context UI

The state-diagram toolbar exposes an execution-context selector when the selected machine has one or more `execution_action_bindings`.

Available projections are:

```text
自動（単一コンテキスト）
Machineのみ
<System> / <entry>
```

Selection is a presentation operation only:

- compiler IR and persisted `io-state-views.json` retain every binding;
- the UI asks `GlyphExecutionContext.actionFor(transition)` for the selected projection;
- diagram labels, enabling-case labels, SVG, PNG, and PDF exports consume the same selected projection;
- the selection is stored per machine in session storage;
- no global network API or compiler state is mutated.

## 6. Boolean branch reasoning

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

## 7. IR version ownership

`glyph/state_transition_contract.py` is the sole owner of transition contract versions.

```text
raw normalized machine IR:       v2
public StateTransitionIR:         v4
Action scope extension:           v1
result-consumer subset analysis:  v2
complete System Action analysis:  v1
```

The scope fields are additive to public v4. The compatibility `action` projection remains available, so existing v4 readers are not forced to migrate immediately.

Raw and public markers are named separately. Compiler stages import the values from the central contract rather than defining competing schema versions.

## 8. Acceptance requirements

The implementation is incomplete unless all of the following hold:

- `x | !x` exhausts its source before the wildcard;
- `x & !x` is removed before the wildcard;
- direct, bound, aliased, nested, and pure-wrapper result flows are recognized;
- a result-independent operation after the machine transition is a System Action;
- an operation before the transition is not attached to the edge;
- mixed post-transition operations preserve execution order and relation metadata;
- a system Action does not appear in `machine_action`;
- divergent systems remain separate bindings;
- the UI can select Machine-only and each concrete system entry;
- context selection changes diagram labels and exports without mutating compiler IR;
- multiple machine calls are diagnosed rather than collapsed;
- synthesized failures do not execute downstream success-path system operations;
- the exact default workspace still renders concrete `actuator(DoorState(...))` Actions;
- compiler, desktop, browser, SVG, PNG, PDF, layout, and snapshot suites pass.

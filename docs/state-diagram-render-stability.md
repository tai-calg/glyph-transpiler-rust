# State diagram render stability

## Problem

The diagram application polls `/api/state` every 900 ms. Before this change, every
successful poll called the base `render()` function even when the compiler snapshot,
selected tab, and selected machine had not changed.

A state graph is not final immediately after the base DOM is inserted. Independent
browser-side passes subsequently perform:

1. transition-label packing and the transition details index;
2. UML transition semantics;
3. input-to-action summary labels;
4. StateTransitionIR v2 label replacement;
5. initial pseudo-transition routing;
6. editable-position restoration and route repair.

Replacing the DOM on every poll exposed the intermediate base graph between these
passes. Users therefore saw raw `T1`, `T2`, and unadjusted routes flash periodically
before the final graph returned.

## Contract

A rendered state diagram now has two phases:

- **pending**: the base DOM exists but is not user-visible;
- **stable**: all required deterministic adjustment passes have completed.

The browser marks a committed graph with:

```text
data-render-stable="true"
```

The graph is revealed only after all of the following are true:

```text
data-label-layout-ready="true"
data-uml-transition-ready="true"
data-transition-input-action-labels-ready="true"
data-state-transition-ir-v2-labels-ready="true"
data-initial-route-ready="true"  # when an initial path exists
```

Two animation frames are allowed after the final signal before revealing the graph,
so style and layout measurements are committed before paint.

## Unchanged snapshot suppression

The presentation layer computes a render key from:

```text
snapshot.version
snapshot.digest
snapshot.status
active tab
selected system
selected machine
```

When this key is unchanged and the view already has content, polling updates the
status only and does not replace the diagram DOM. This preserves:

- the fully adjusted graph;
- manual node positions;
- selection state;
- scroll state;
- route and label measurements.

A real source, status, tab, system, or machine change still produces a new graph.
That graph remains hidden until it reaches the stable phase.

## Failure policy

The barrier is presentation-only and must not leave the application permanently
blank if an optional browser pass fails. After 1600 ms, the graph is revealed as a
conservative fallback and marked:

```text
data-render-stable-state="fallback"
```

The timeout is deliberately longer than the normal adjustment chain and is not used
for successful rendering.

## Validation

The browser regression performs both cases:

1. waits through more than two 900 ms polling cycles and verifies that the committed
   graph-stage DOM node is not replaced;
2. forces a genuine state-view rebuild and verifies that the new graph is hidden
   while pending, then becomes visible only with final labels and a routed initial
   transition.

The test compiles and runs the real application with Chromium and records a final
screenshot under `build/state-diagram-stability/`.

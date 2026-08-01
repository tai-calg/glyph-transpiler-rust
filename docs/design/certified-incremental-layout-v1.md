# Certified Incremental Diagram Layout v1

## Status

This document defines the publication-grade geometry contract for Glyph Studio state diagrams.

The design has two simultaneous goals:

1. never publish a layout that violates a declared hard constraint;
2. preserve real-time editing by reusing certificates, repairing only dirty geometry, and yielding between bounded work slices.

It does **not** claim globally optimal graph drawing. It claims fail-closed publication for the supported geometry model.

## 1. Geometry model

A rendered diagram is represented by:

```text
D = (N, E, L, P, V)
```

where:

- `N` is the set of state-node rectangles;
- `E` is the set of serialized SVG routes;
- `L` is the set of transition-label rectangles;
- `P` is the set of route ports and the initial pseudo-state marker;
- `V` is the finite canvas rectangle.

A layout configuration is:

```text
C = (node positions, label positions, route path data, canvas size)
```

The renderer is a quantizing map:

```text
Q : C -> rendered SVG geometry
```

`Q` includes decimal serialization, browser SVG interpretation and final DOM dimensions. A pre-quantized candidate is therefore not sufficient evidence of correctness.

## 2. Hard constraints

Publication requires all supported hard constraints to hold on `Q(C)`.

### 2.1 Containment

Every node, label, marker and route point lies inside the canvas safety boundary.

### 2.2 Separation

- labels do not overlap other labels;
- labels do not overlap state nodes;
- a route does not cross a non-endpoint state node;
- a route does not cross a foreign transition label.

### 2.3 Route integrity

- the initial pseudo-transition does not cross a normal transition;
- its minimum clearance from normal transitions is at least the configured margin;
- the marker and route are attached to the same certified candidate;
- every displayed transition retains a corresponding route.

### 2.4 Semantic fidelity

Line wrapping, localization and layout must not change the canonical Input, Guard, Action, Output or failure text.

### 2.5 Locality

A transition label remains within the declared tether distance from its route anchor.

A configuration that violates any hard constraint is not assigned a publication certificate. Hard violations are never converted into a finite penalty and accepted as a “best” result.

## 3. Soft objectives

After feasibility is established, the solver minimizes a lexicographically ordered cost:

```text
E(C) = (
  manual-position displacement,
  total route crossings,
  obstacle clearance deficit,
  route length,
  bend count,
  automatic-position displacement
)
```

The first component is considered before later components. Hard constraints remain outside `E`.

## 4. Rendered-geometry certification

### 4.1 Versioned path interpretation

The shared geometry kernel parses the final serialized SVG `d` string. Supported commands are flattened to polylines using recursive de Casteljau subdivision.

A curve segment is subdivided until both conditions hold:

```text
flatness <= epsilon_curve
chord_length <= epsilon_length
```

The current defaults are:

```text
epsilon_curve = 0.35 px
epsilon_length = 3 px
```

The certificate is computed from this flattened form of the **serialized path**, not from the unrounded candidate coordinates.

### 4.2 Obstacle inflation

A required visual margin `m` is represented as an inflated obstacle:

```text
O' = O (+) B(m)
```

where `(+)` is the Minkowski sum and `B(m)` is the radius-`m` axis-aligned safety region used by the current rectangular obstacle model.

### 4.3 Certificate

A route certificate contains at least:

```text
geometry fingerprint
constraint version
crossing count
minimum clearance
candidate count
exactly audited candidate count
work-slice metrics
```

The certificate is valid only when all relevant hard predicates return true.

## 5. Incremental solving

Full recomputation on every editor update is prohibited.

### 5.1 Dependency fingerprint

Each certificate is bound to a fingerprint containing the geometry it depends on:

```text
source/program digest
canvas dimensions
node rectangles
label rectangles
serialized route paths
selected Machine
layout generation
```

If the fingerprint is unchanged, the certificate is reused without route search.

### 5.2 Dirty-set repair

Changes are classified into dirty sets:

```text
D_node
D_label
D_route
D_viewport
D_semantics
```

The intended repair order is:

1. reuse the previous certified configuration;
2. update changed text dimensions;
3. repair labels whose constraints became invalid;
4. repair routes whose obstacles or endpoints changed;
5. perform a global bounded solve only if local repair cannot produce a certificate.

The current v1 implementation applies this principle through path flattening caches, geometry fingerprints, retained manual positions and a local initial-route candidate bank. Later route solvers must use the same contract.

## 6. Real-time execution contract

Correctness work may span multiple frames, but it must not monopolize the UI thread.

### 6.1 Work slices

Potentially unbounded candidate or audit loops use a frame budget:

```text
interactive work slice <= 8 ms target
```

When the budget is consumed, work yields through `requestAnimationFrame` and resumes with the same generation token.

The target is a scheduling contract, not a hard wall-clock theorem: browser scheduling and individual primitive calls can exceed the target. The implementation records maximum observed slice duration so regressions are measurable.

### 6.2 Cancellation

Every asynchronous solve is bound to a monotonically increasing generation. A newer edit invalidates the older generation. Stale work may not publish a certificate or mutate the final route.

### 6.3 Two-stage route selection

Route search uses:

1. a cheap analytic filter and ranking over all candidates;
2. exact rendered-path certification in ranked order.

The exact stage stops at the first certified candidate. If no early candidate succeeds, it continues in bounded frame slices rather than blocking the editor.

### 6.4 Cached geometry

Flattened route geometry is cached by the path element, serialized `d` value and flattening parameters. Repeated publication audits therefore avoid reparsing unchanged paths.

## 7. Publication state machine

```text
pending
  -> valid
  -> failed
```

- `pending`: a current-generation certificate is not yet available;
- `valid`: all hard predicates passed for the current fingerprint;
- `failed`: one or more hard predicates failed or the geometry kernel failed.

A failure sets publication readiness to false. The UI may retain the previous visual frame while solving, but it may not represent stale geometry as certified for the current generation.

## 8. Required diagnostics

A failed solve must report structured reasons such as:

```text
missing-initial-route
initial-route-crossing
initial-route-clearance
route-node
route-foreign-label
label-collision
node-collision
outside-stage
tether-distance
semantic-text-mismatch
geometry-kernel-error
```

Timeouts and budget yields are performance diagnostics, not proof substitutes.

## 9. Validation strategy

### 9.1 Static contracts

Tests verify that:

- every publication router uses the shared geometry kernel;
- exact rendered-path certification occurs after serialization;
- frame-budget and generation cancellation are present;
- certificate failure is fail-closed;
- enhancers are idempotent;
- injected JavaScript is syntactically valid.

### 9.2 Browser contracts

Representative diagrams must verify:

- zero initial-route crossings;
- minimum route clearance;
- no non-endpoint node crossing;
- no foreign-label crossing;
- valid final publication certificate;
- cache reuse for an unchanged re-run;
- bounded maximum work-slice duration;
- no browser or page errors.

### 9.3 Adversarial cases

The suite should include:

- dense parallel transitions;
- self-loops around the initial state;
- long unbroken identifiers;
- narrow viewports;
- repeated live-preview updates with the same transition count;
- node and label manual moves;
- quantization-sensitive routes near an obstacle boundary.

## 10. Non-claims and extension boundary

The current model does not prove aesthetic optimality, arbitrary SVG command support, planarity of every normal transition, or globally optimal routing.

Future orthogonal-grid or visibility-graph routers may replace the candidate generator. They must still:

- produce serialized paths through the shared geometry kernel;
- obey the same hard constraints;
- publish only after final rendered-geometry certification;
- support generation cancellation and frame-budgeted continuation;
- preserve certificate and diagnostic compatibility.

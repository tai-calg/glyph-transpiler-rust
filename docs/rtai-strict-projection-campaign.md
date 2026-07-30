# RTAI strict projection campaign

## Purpose

This campaign proves that a supported Glyph program can publish System Actions
without executing or falling back to the legacy System Action analyzer.

The default application pipeline remains `shadow`. Strict mode is an explicit,
fail-closed migration path until the public Effect surface is fully contracted and
the default switch is approved.

## Implemented chain

```text
verified Effect contracts
  -> reachable Effect contract audit
  -> finite exhaustive or reviewed targeted inputs
  -> independent TEIR concrete replay
  -> same-edge and completion-class witnesses
  -> native RTAI Evidence
  -> Exact / May / Unknown classification
  -> exact-action checker
  -> strict System Action projection
  -> browser and authenticated Desktop campaigns
```

## Verified Effect contracts

`VerifiedEffectContract` couples three reviewed facts:

- an exact abstract `EffectSummary`
- an explicit concrete replay handler
- a source string identifying the reviewed contract

A contract is rejected when its operation does not match the summary, the summary
is not exact, the write footprint is unknown, or completion contains `unknown`.
Concrete replay never synthesizes an Effect handler from the Glyph declaration.

`VerifiedEffectContractRegistry` supports default and System-entry-specific
contracts. An entry-specific contract does not leak to another entry.

## Reachable Effect contract audit

`audit_effect_contract_coverage` traverses the TEIR call graph from every System
entry and collects each reachable external Effect. The strict campaign is blocked
when:

- a reachable Effect has no entry-visible verified contract
- a reachable function has a TEIR lowering issue
- the contract audit is not configured

The audit is deliberately conservative. It does not use solver reachability to omit
an external boundary contract.

This infrastructure defines and enforces the supported Effect surface. It does not
invent semantics for unreviewed production Effects. The current strict acceptance
surface contains a reviewed read-only identity `actuator` contract; additional
public Effects must receive real reviewed contracts before they are added to the
strict release surface.

## Automatic and targeted witnesses

`generate_bounded_system_witnesses` first attempts exhaustive finite
Bool/Product/Sum enumeration. It retains witnesses keyed by:

```text
System entry + normalized Machine edge + completion class
```

When the finite domain is unsupported or exceeds the case budget, a
`TargetedWitnessRegistry` may provide reviewed concrete inputs. Each targeted case
records:

- System entry
- ordered concrete arguments
- review source
- optional human-readable label

Targeted cases prove only concrete existence. They do not claim exhaustive input
coverage or upgrade Effect trace, cardinality, or completion evidence. Those
properties remain owned by abstract Evidence.

The witness report distinguishes:

- `finite-exhaustive`
- `targeted-existence`
- complete generation
- exhaustive generation
- incomplete or failed generation

Missing targets, arity mismatch, missing Effect handlers, replay failure, and
contract-handler failure all fail closed.

## Exact / May / Unknown

`attach_rtai_semantic_status` classifies each rendered transition using only native
Evidence and the independent readiness gate:

- `Exact`: all exact projection conditions pass
- `May`: execution remains possible, but exact projection is not proven
- `Unknown`: a native Evidence context, rendered-edge binding, or required property
  remains unresolved

The UI pass projects this field without re-running AST, CFG, solver, or legacy
analysis:

- strict-exact mode shows the status badge continuously
- shadow mode exposes May or Unknown on transition-card hover/selection
- the tooltip includes the Evidence rejection reason

The visible badge is attached to the rendered transition I/O card, not the hidden
legacy label.

## Strict projection

`EvidenceProjectionMode.STRICT_EXACT` with
`rtai_execution_evidence_v2` is fail closed:

- exact native Evidence supplies `system_action`
- unready Evidence supplies no System Action
- `legacy_system_action_fallback_allowed` is false
- legacy execution bindings and contexts are removed
- Machine-owned `action` remains unchanged

`build_strict_io_state_views` constructs the raw I/O and Machine views and calls
the StateTransitionIR pipeline directly in strict mode. In this path:

```text
rtai_legacy_system_action_analyzer_enabled = false
```

The legacy System Action analyzer and legacy Evidence adapter are not executed.
Their source files remain because the default application path still uses shadow
compatibility.

## Browser campaigns

The I/O State Diagram Snapshot workflow verifies three semantic UI states.

### Exact

`tests/verify_rtai_strict_projection_ui.mjs` runs the strict acceptance program and
requires:

- strict campaign readiness
- complete Effect contract coverage
- complete concrete witness generation
- native Evidence as the only System Action source
- no legacy Evidence, bindings, or contexts
- a visible `Exact` badge on every transition I/O card
- the rendered Action contains the contract-backed Effect

Artifacts:

```text
build/rtai-strict-projection/io-state-views.json
build/rtai-strict-projection/strict-ui.png
build/rtai-strict-projection/strict-ui-report.json
```

### May and Unknown

`tests/verify_rtai_semantic_status_ui.mjs` verifies:

- `Unknown` for the normal shadow application without Effect contracts
- hover-visible Unknown badges without changing the README baseline layout
- `May` for a large finite domain with complete Effect contracts but no concrete
  reachability witness
- no System Action projection for the May case
- continuously visible May badges in strict-exact fail-closed mode

Artifacts:

```text
build/rtai-semantic-status/unknown-hover.png
build/rtai-semantic-status/may-ui.png
build/rtai-semantic-status/report.json
```

## Desktop campaign

`create_desktop_server` accepts the same view-builder dependency as the browser
application. The Desktop contract test runs the strict view builder through the
authenticated loopback sidecar and requires:

- strict-exact output
- legacy analyzer disabled
- strict campaign ready
- native Evidence System Actions
- Exact transition status
- no legacy Evidence
- the semantic-status UI installed in the served application

The Desktop workflow additionally builds the trusted frontend and Python sidecar,
checks the Tauri Rust shell, and verifies Rust formatting.

## Remaining before default application activation

- define reviewed contracts for every Effect included in the intended public strict
  release surface
- add reviewed targeted cases or solver-model witness providers for every supported
  non-finite or oversized input domain
- complete any recursive-summary or ownership/lifetime precision specifically
  required by that release surface
- switch the normal application configuration from `shadow` to `strict-exact`
- remove shadow compatibility after the strict default campaign is stable
- delete legacy analyzer modules after no supported path references them

General unbounded SMT, precise analysis of all recursive programs, and complete
place/lifetime semantics remain separate precision work. Unsupported cases must
continue to fail closed as `Unknown`; they are not prerequisites for a bounded,
explicitly supported strict release surface.

# RTAI strict projection campaign

## Purpose

This campaign proves that a supported Glyph program can publish System Actions
without executing or falling back to the legacy System Action analyzer.

The default application pipeline remains `shadow`. Strict mode is an explicit,
fail-closed migration path until the selected public Effect surface remains stable
and the default switch is approved.

## Implemented chain

```text
reviewed public Effect surface
  -> exact return / failure / external-store contracts
  -> reachable outbound Effect contract audit
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

`VerifiedEffectContract` couples reviewed abstract and concrete semantics:

- an exact abstract `EffectSummary`
- an explicit concrete replay handler
- the exact return relation represented by the abstract value DAG
- the declared failure vocabulary
- the external read and write footprint
- a source string and review note identifying the contract decision

A contract is rejected when its operation does not match the summary, the summary
is not exact, the write footprint is unknown, or completion contains `unknown`.
Concrete replay never synthesizes an Effect handler from a Glyph declaration.

`reviewed_deterministic_contract` constructs deterministic release contracts with
an explicit return value and concrete external-store writes. The proof kind is
`reviewed-contract`; it is distinct from structural identity.

`VerifiedEffectContractRegistry` supports default and System-entry-specific
contracts. An entry-specific contract does not leak to another entry.

## Public strict Effect surface v1

The normative catalog is `glyph/transition_analysis/public_effect_contracts.py`.
Every included source is compiled in CI, its reachable outbound Effect set is
compared with the catalog, and each reviewed handler is replayed against a concrete
case. Contract IR exposes the return value, failure vocabulary and external writes.

### Included

| Public source | System entry | Effect | Return contract | Failure contract | External state change |
|---|---|---|---|---|---|
| built-in first-run workspace | `DoorControl.control` | `actuator(state)` | `Receipt(state)` | no failure channel | `door-actuator.current-state := state` |
| `examples/acceptance/motor_safety.glyph` | `MotorSafety.cycle` | `write_motor(command)` | `Receipt(command)` | no failure channel | `motor.command := command` |
| `examples/acceptance/job_scheduler.glyph` | `BatchRuntime.run` | `submit_batch(layout)` | `SubmitReceipt(layout.lane)` | no failure channel | `batch-runtime.last-submission := layout` |
| `examples/door_sketch.glyph` | `Door.control` | `lock(command)` | `true` acknowledgement | no failure channel | `door.lock-command := command` |
| `examples/door_sketch.glyph` | `Door.control` | `log(command)` | `true` acknowledgement | no failure channel | `door.log-command := command` |
| `examples/acceptance/rtai_strict_projection.glyph` | `DoorControl.control` | `actuator(state)` | identity `state` | no failure channel | none; read-only strict fixture |

“No failure channel” is a real contract constraint, not an assumption that Host
failures never occur. A Host implementation that can fail must change the Glyph
Effect type and receive a new reviewed contract before strict projection.

### Explicitly excluded

| Source | Effect | Why it is excluded from strict v1 |
|---|---|---|
| `examples/acceptance/door_controller.glyph` | `lock`, `alarm` | `Receipt|ControlError` is declared, but the operation-specific error set and whether external state changes before each failure are not specified |
| `examples/system_controller.glyph` | `write_actuator` | `Cycle|Error` is declared without a reviewed `Actuator` failure relation or failure-time external store; `report_violation` is not reachable from `cycle` |
| `examples/controller.glyph` | `exec` | there is no explicit public `system` entry, so strict System execution projection has no context |

These exclusions prevent a successful sample handler from being misused as proof
that all executions succeed. Failure-capable Effects are admitted only after the
abstract domain can represent their exact result alternatives and the Host contract
specifies success and failure store transforms.

README-only signatures such as `save_file` are syntax illustrations, not strict
release entries. They have no compiled System context or reviewed Host contract.

## Reachable Effect contract audit

`audit_effect_contract_coverage` traverses the TEIR call graph from every System
entry and collects each reachable outbound `!Effect`. The strict campaign is
blocked when:

- a reachable Effect has no entry-visible verified contract
- a reachable function has a TEIR lowering issue
- the contract audit is not configured

Glyph currently represents `ext` inputs and `!` Effects with the same internal
declaration class. Audit version 2 preserves the source-level distinction: top-level
`ext` calls are inbound inputs and are not accepted as outbound Effect coverage.
This prevents a sensor or panel input handler from being mistaken for a System
Action contract.

The audit is deliberately conservative. It does not use solver reachability to omit
an external boundary contract.

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

The I/O State Diagram Snapshot workflow verifies the public contract catalog and
three semantic UI states.

### Public contract gate

`tests/test_public_strict_effect_contracts.py` requires:

- every included public source compiles
- reachable outbound Effects equal the catalog exactly
- inbound `ext` inputs are not counted as Effects
- contract parameter order matches the Glyph declaration
- concrete replay returns the reviewed value
- failure vocabulary and completion match the reviewed contract
- every external write has a named singleton location and reviewed value
- excluded failure-capable sources remain incomplete without fabricated contracts

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

- decide whether each explicitly excluded failure-capable Effect is part of the
  intended strict release; if so, define its exact success/failure return relation
  and success/failure external-store transforms
- add reviewed targeted cases or solver-model witness providers for any selected
  public entry whose finite input domain exceeds the campaign budget
- complete only the recursive-summary or ownership/lifetime precision required by
  the selected release surface
- switch the normal application configuration from `shadow` to `strict-exact` for
  the cataloged surface
- remove shadow compatibility after the strict default campaign is stable
- delete legacy analyzer modules after no supported path references them

General unbounded SMT, precise analysis of all recursive programs, and complete
place/lifetime semantics remain separate precision work. Unsupported cases must
continue to fail closed as `Unknown`; they are not prerequisites for a bounded,
explicitly supported strict release surface.

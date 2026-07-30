# RTAI strict projection campaign

## Purpose

This campaign proves that a supported Glyph program can publish System Actions
without executing or falling back to the legacy System Action analyzer.

The default application pipeline remains `shadow`. Strict mode is an explicit,
fail-closed migration path.

## Implemented chain

```text
verified Effect contracts
  -> finite System-entry input enumeration
  -> independent TEIR concrete replay
  -> same-edge and completion-class witnesses
  -> native RTAI Evidence
  -> exact-action checker
  -> strict System Action projection
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

## Automatic bounded witnesses

`generate_bounded_system_witnesses` enumerates finite Bool/Product/Sum inputs for
System entry functions. It executes TEIR with only handlers from the verified
contract registry and retains witnesses keyed by:

```text
System entry + normalized Machine edge + completion class
```

A non-finite domain, missing Effect handler, execution error, or case-budget limit
makes the generation report incomplete. No incomplete case is converted into an
exact witness.

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
Their source files remain in the repository because the default public Alpha path
still uses shadow compatibility.

## Snapshot campaign

The I/O State Diagram Snapshot workflow runs:

```text
python tests/verify_rtai_strict_projection_snapshot.py
```

against `examples/acceptance/rtai_strict_projection.glyph` and a reviewed
read-only identity `actuator` contract.

The verifier requires:

- the strict campaign is ready
- automatic witness generation is complete
- the legacy analyzer is disabled
- legacy fallback is disabled
- no legacy Evidence or execution bindings remain
- every rendered transition obtains its System Action from native RTAI Evidence

The generated contract artifact is:

```text
build/rtai-strict-projection/io-state-views.json
```

## Remaining before default application activation

- define reviewed contracts for the production Effect surface
- add targeted witness generation for non-finite or large domains
- run strict rendered-UI and desktop application campaigns
- expose Exact / May / Unknown states clearly in the UI
- switch the normal application configuration from `shadow` to `strict-exact`
- remove legacy analyzer modules after no supported default path references them

General unbounded SMT, precise analysis of all recursive programs, and complete
place/lifetime semantics remain separate precision work. Unsupported cases must
continue to fail closed as `unknown`; they are not prerequisites for a bounded,
explicitly supported strict release surface.

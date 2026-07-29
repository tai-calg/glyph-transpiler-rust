from __future__ import annotations


STATE_TRANSITION_IR_SCHEMA = "glyph.state-transition-ir"

# The raw compiler stage contains normalized state edges before condition-role,
# input-preimage, enabling-case, and execution-context enrichment.
RAW_STATE_TRANSITION_IR_VERSION = 2

# Public StateTransitionIR v5 separates intrinsic machine operations from
# system-entry operations and publishes an explicit display projection.
STATE_TRANSITION_IR_VERSION = 5

# Input [Guard] ➞ Action remains label contract v2. Scope separation has its own
# additive version and does not redefine the label grammar.
TRANSITION_SEMANTICS_VERSION = 2
TRANSITION_INPUT_PREIMAGE_VERSION = 1
TRANSITION_ENABLING_CASES_VERSION = 1
TRANSITION_OPERATION_ACTION_VERSION = 2
TRANSITION_RESULT_CONSUMER_ACTION_VERSION = 2
TRANSITION_ACTION_SCOPE_VERSION = 1
TRANSITION_ACTION_TARGET_INDEPENDENCE_VERSION = 1


def raw_transition_ir_marker() -> dict[str, object]:
    return {
        "schema": STATE_TRANSITION_IR_SCHEMA,
        "version": RAW_STATE_TRANSITION_IR_VERSION,
        "stage": "normalized-machine",
    }


def public_transition_ir_marker() -> dict[str, object]:
    return {
        "schema": STATE_TRANSITION_IR_SCHEMA,
        "version": STATE_TRANSITION_IR_VERSION,
        "stage": "public",
    }

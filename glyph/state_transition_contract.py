from __future__ import annotations


STATE_TRANSITION_IR_SCHEMA = "glyph.state-transition-ir"

# The raw compiler stage contains normalized state edges before condition-role,
# input-preimage, enabling-case, and execution-context enrichment.
RAW_STATE_TRANSITION_IR_VERSION = 2

# Action-scope fields are additive to the public v4 shape. Existing `action`
# remains the selected display projection, while explicit fields expose machine
# and system ownership without invalidating v4 consumers.
STATE_TRANSITION_IR_VERSION = 4

# Input [Guard] ➞ Action remains label contract v2. Scope separation has its own
# additive version and does not redefine the label grammar.
TRANSITION_SEMANTICS_VERSION = 2
TRANSITION_INPUT_PREIMAGE_VERSION = 1
TRANSITION_ENABLING_CASES_VERSION = 1
TRANSITION_OPERATION_ACTION_VERSION = 2
# Result-dependency remains an explicitly identified subset for compatibility.
TRANSITION_RESULT_CONSUMER_ACTION_VERSION = 2
# v1 means every proven operation sequenced after the machine transition is a
# System Action. Path completeness is versioned separately below.
TRANSITION_SYSTEM_EXECUTION_ACTION_VERSION = 1
TRANSITION_ACTION_SCOPE_VERSION = 1
TRANSITION_ACTION_TARGET_INDEPENDENCE_VERSION = 1
# New additive contracts. They do not reinterpret the existing v1 fields.
TRANSITION_EXECUTION_CONTEXT_CONTROL_FLOW_VERSION = 1
TRANSITION_EXECUTION_CONTEXT_PROJECTION_VERSION = 1


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
    }

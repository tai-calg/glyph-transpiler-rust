from __future__ import annotations

# Compatibility import. Execution control flow, argument provenance, and
# correctness-critical projection guards are centralized in one implementation.
from .transition_system_execution_control_flow_v2 import (
    attach_transition_system_execution_actions,
)


__all__ = ["attach_transition_system_execution_actions"]

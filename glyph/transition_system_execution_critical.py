from __future__ import annotations

# Compatibility import. Correctness-critical validation now lives in the
# execution-control-flow implementation instead of a second post-processing pass.
from .transition_system_execution_control_flow_v2 import (
    attach_transition_system_execution_actions,
)


__all__ = ["attach_transition_system_execution_actions"]

from __future__ import annotations

# Stable import surface; execution analysis and safety policy are implemented in
# transition_system_execution_control_flow.
from .transition_system_execution_control_flow import (
    attach_transition_result_consumer_actions,
    attach_transition_system_execution_actions,
)


__all__ = [
    "attach_transition_system_execution_actions",
    "attach_transition_result_consumer_actions",
]

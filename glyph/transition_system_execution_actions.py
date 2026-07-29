from __future__ import annotations

from .artifacts import CompilationModel
from .transition_system_execution_control_flow import (
    attach_transition_system_execution_actions,
)


def attach_transition_result_consumer_actions(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Compatibility entry point for the former result-consumer-only analysis."""

    return attach_transition_system_execution_actions(model, machine_view)


__all__ = [
    "attach_transition_system_execution_actions",
    "attach_transition_result_consumer_actions",
]

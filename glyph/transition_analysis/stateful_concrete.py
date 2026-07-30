from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from ..artifacts import CompilationModel
from .concrete import (
    ConcreteExecutionResult,
    ConcreteInterpreter,
    EffectEvent,
    EffectHandler,
)


ConcreteStoreLocation = tuple[str, str]


@dataclass(frozen=True)
class StatefulEffectResult:
    value: object
    writes: tuple[tuple[ConcreteStoreLocation, object], ...] = ()


StatefulEffectHandler = Callable[[tuple[object, ...]], object | StatefulEffectResult]


@dataclass(frozen=True)
class StatefulConcreteExecutionResult:
    return_value: object | None
    transition_trace: tuple[object, ...]
    effect_trace: tuple[object, ...]
    completion: str
    error: object | None
    final_store: tuple[tuple[ConcreteStoreLocation, object], ...]


class StatefulConcreteInterpreter(ConcreteInterpreter):
    """Concrete TEIR interpreter whose Effect handlers can update a test store."""

    def __init__(
        self,
        model: CompilationModel,
        *,
        effect_handlers: Mapping[str, StatefulEffectHandler] | None = None,
        initial_store: Mapping[ConcreteStoreLocation, object] | None = None,
        max_steps: int = 10_000,
        max_call_depth: int = 128,
    ) -> None:
        handlers: Mapping[str, EffectHandler] = dict(effect_handlers or {})  # type: ignore[assignment]
        super().__init__(
            model,
            effect_handlers=handlers,
            max_steps=max_steps,
            max_call_depth=max_call_depth,
        )
        self._initial_store = dict(initial_store or {})
        self._concrete_store: dict[ConcreteStoreLocation, object] = {}

    def run(self, function_name: str, arguments: object) -> StatefulConcreteExecutionResult:
        self._concrete_store = dict(self._initial_store)
        result: ConcreteExecutionResult = super().run(function_name, arguments)  # type: ignore[arg-type]
        return StatefulConcreteExecutionResult(
            result.return_value,
            result.transition_trace,
            result.effect_trace,
            result.completion,
            result.error,
            tuple(sorted(self._concrete_store.items(), key=lambda item: item[0])),
        )

    def _invoke_effect(
        self,
        operation: str,
        arguments: tuple[object, ...],
    ) -> object:
        handler = self.effect_handlers.get(operation)
        if handler is None:
            return super()._invoke_effect(operation, arguments)
        raw = handler(arguments)
        if isinstance(raw, StatefulEffectResult):
            result = raw.value
            for location, value in raw.writes:
                self._concrete_store[location] = value
        else:
            result = raw
        self._effects.append(EffectEvent(operation, arguments, result))
        return result

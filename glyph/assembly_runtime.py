from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from .assembly import MachineAssemblyIR
from .compiler import GlyphError


@dataclass(frozen=True)
class EffectEmission:
    effect: str
    value: object


@dataclass(frozen=True)
class ReactionTraceEntry:
    instance: str
    input: str
    value: object
    depth: int


@dataclass(frozen=True)
class ExternalEffect:
    instance: str
    effect: str
    value: object


@dataclass(frozen=True)
class ImmediateReactionResult:
    trace: tuple[ReactionTraceEntry, ...]
    external_effects: tuple[ExternalEffect, ...]


ReactionHandler = Callable[[str, str, object], Iterable[EffectEmission]]


class ImmediateAssemblyRuntime:
    """Reference executor for assembly v1 immediate causal propagation.

    A reaction handler executes one local Machine reaction and returns its `!`
    effects in source order. Routed effects recursively invoke the target Machine
    before the source reaction continues to its next emitted effect. Unrouted
    effects remain Host-facing external effects.
    """

    def __init__(self, ir: MachineAssemblyIR):
        self.ir = ir
        self._instances = {str(item["name"]) for item in ir.instances}
        self._routes: dict[tuple[str, str], Mapping[str, object]] = {}
        for route in ir.routes:
            key = (str(route["source_instance"]), str(route["effect"]))
            if key in self._routes:
                raise GlyphError(
                    f"assembly IRに重複routeがある: {key[0]}.{key[1]}"
                )
            self._routes[key] = route

    def react(
        self,
        instance: str,
        input_name: str,
        value: object,
        handler: ReactionHandler,
    ) -> ImmediateReactionResult:
        if instance not in self._instances:
            raise GlyphError(f"assembly instance '{instance}' が存在しない")

        trace: list[ReactionTraceEntry] = []
        external: list[ExternalEffect] = []
        active: list[str] = []

        def invoke(target: str, target_input: str, payload: object) -> None:
            if target in active:
                chain = " -> ".join((*active, target))
                raise GlyphError(f"即時Machine反応の再入は禁止: {chain}")

            active.append(target)
            trace.append(
                ReactionTraceEntry(
                    instance=target,
                    input=target_input,
                    value=payload,
                    depth=len(active) - 1,
                )
            )
            try:
                emissions = tuple(handler(target, target_input, payload))
                for emission in emissions:
                    route = self._routes.get((target, emission.effect))
                    if route is None:
                        external.append(
                            ExternalEffect(
                                instance=target,
                                effect=emission.effect,
                                value=emission.value,
                            )
                        )
                        continue
                    invoke(
                        str(route["target_instance"]),
                        str(route["input"]),
                        emission.value,
                    )
            finally:
                active.pop()

        invoke(instance, input_name, value)
        return ImmediateReactionResult(tuple(trace), tuple(external))

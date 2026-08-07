from __future__ import annotations

from dataclasses import dataclass
from types import GeneratorType
from typing import Callable, Generator, Mapping

from .assembly import MachineAssemblyIR
from .compiler import GlyphError


@dataclass(frozen=True)
class EffectInvocation:
    effect: str
    arguments: tuple[object, ...]

    def __init__(self, effect: str, *arguments: object):
        object.__setattr__(self, "effect", effect)
        object.__setattr__(self, "arguments", tuple(arguments))


@dataclass(frozen=True)
class ReactionTraceEntry:
    phase: str
    instance: str
    input: str
    value: object
    depth: int
    state: object


@dataclass(frozen=True)
class ExternalEffect:
    instance: str
    effect: str
    arguments: tuple[object, ...]
    result: object


@dataclass(frozen=True)
class ImmediateReactionResult:
    trace: tuple[ReactionTraceEntry, ...]
    external_effects: tuple[ExternalEffect, ...]
    states: dict[str, object]


ReactionGenerator = Generator[EffectInvocation, object, object]
ReactionHandler = Callable[[str, str, object, object], ReactionGenerator]
HostExecutor = Callable[[str, str, tuple[object, ...]], object]


class ImmediateAssemblyRuntime:
    """Stateful reference executor for Assembly v1 immediate propagation.

    Each handler receives the instance's current state and returns its next state.
    A yielded routed operation suspends the source generator, runs the target
    reaction to completion, and resumes the source with unit (`None`). A yielded
    unrouted operation is executed by the Host executor and its result is sent back
    into the source generator.

    Machine states are updated in a working configuration and committed together
    only when the complete top-level causal reaction succeeds. External Host
    effects are observable and cannot be rolled back.
    """

    def __init__(
        self,
        ir: MachineAssemblyIR,
        initial_states: Mapping[str, object],
    ) -> None:
        self.ir = ir
        self._instances = {
            str(item["name"]): item
            for item in ir.instances
        }
        expected = set(self._instances)
        provided = set(initial_states)
        if provided != expected:
            missing = sorted(expected - provided)
            extra = sorted(provided - expected)
            details: list[str] = []
            if missing:
                details.append("missing=" + ",".join(missing))
            if extra:
                details.append("extra=" + ",".join(extra))
            raise GlyphError(
                "Assembly初期状態は全instanceを一度ずつ指定する: "
                + " ".join(details)
            )
        self._states = dict(initial_states)
        self._routes: dict[tuple[str, str], Mapping[str, object]] = {}
        for route in ir.routes:
            key = (str(route["source_instance"]), str(route["effect"]))
            if key in self._routes:
                raise GlyphError(
                    f"assembly IRに重複routeがある: {key[0]}.{key[1]}"
                )
            self._routes[key] = route

    @property
    def states(self) -> dict[str, object]:
        return dict(self._states)

    def _input_names(self, instance: str) -> set[str]:
        raw = self._instances[instance].get("inputs", [])
        return {
            str(item["name"])
            for item in raw
            if isinstance(item, Mapping) and "name" in item
        }

    def _allowed_effects(self, instance: str) -> set[str]:
        raw = self._instances[instance].get("allowed_effects", [])
        return {str(item) for item in raw}

    def react(
        self,
        instance: str,
        input_name: str,
        value: object,
        handler: ReactionHandler,
        host_executor: HostExecutor | None = None,
    ) -> ImmediateReactionResult:
        if instance not in self._instances:
            raise GlyphError(f"assembly instance '{instance}' が存在しない")
        if input_name not in self._input_names(instance):
            available = ", ".join(sorted(self._input_names(instance))) or "<none>"
            raise GlyphError(
                f"instance '{instance}' に入力 '{input_name}' がない。使用可能: {available}"
            )

        working = dict(self._states)
        trace: list[ReactionTraceEntry] = []
        external: list[ExternalEffect] = []
        active: list[str] = []

        def invoke(target: str, target_input: str, payload: object) -> None:
            if target in active:
                chain = " -> ".join((*active, target))
                raise GlyphError(f"即時Machine反応の再入は禁止: {chain}")
            if target not in self._instances:
                raise GlyphError(f"assembly instance '{target}' が存在しない")
            if target_input not in self._input_names(target):
                raise GlyphError(
                    f"instance '{target}' に入力 '{target_input}' がない"
                )

            active.append(target)
            depth = len(active) - 1
            before = working[target]
            trace.append(
                ReactionTraceEntry(
                    phase="enter",
                    instance=target,
                    input=target_input,
                    value=payload,
                    depth=depth,
                    state=before,
                )
            )
            try:
                reaction = handler(target, target_input, payload, before)
                if not isinstance(reaction, GeneratorType):
                    raise GlyphError(
                        "Assembly reaction handlerはEffectInvocationをyieldし、"
                        "next stateをreturnするgeneratorである必要がある"
                    )

                try:
                    invocation = next(reaction)
                    while True:
                        if not isinstance(invocation, EffectInvocation):
                            raise GlyphError(
                                f"instance '{target}' のreactionが"
                                "EffectInvocation以外をyieldした"
                            )
                        if invocation.effect not in self._allowed_effects(target):
                            raise GlyphError(
                                f"effect '{invocation.effect}' はMachine instance "
                                f"'{target}' の遷移Actionとして宣言されていない"
                            )

                        route = self._routes.get((target, invocation.effect))
                        if route is not None:
                            if len(invocation.arguments) != 1:
                                raise GlyphError(
                                    f"内部route effect '{target}.{invocation.effect}' は"
                                    "payload引数を1つ必要とする"
                                )
                            invoke(
                                str(route["target_instance"]),
                                str(route["input"]),
                                invocation.arguments[0],
                            )
                            effect_result: object = None
                        else:
                            if host_executor is None:
                                raise GlyphError(
                                    f"外部effect '{target}.{invocation.effect}' を"
                                    "実行するHost executorがない"
                                )
                            effect_result = host_executor(
                                target,
                                invocation.effect,
                                invocation.arguments,
                            )
                            external.append(
                                ExternalEffect(
                                    instance=target,
                                    effect=invocation.effect,
                                    arguments=invocation.arguments,
                                    result=effect_result,
                                )
                            )
                        invocation = reaction.send(effect_result)
                except StopIteration as completed:
                    next_state = completed.value

                working[target] = next_state
                trace.append(
                    ReactionTraceEntry(
                        phase="commit",
                        instance=target,
                        input=target_input,
                        value=payload,
                        depth=depth,
                        state=next_state,
                    )
                )
            finally:
                active.pop()

        invoke(instance, input_name, value)
        self._states = working
        return ImmediateReactionResult(
            trace=tuple(trace),
            external_effects=tuple(external),
            states=dict(self._states),
        )

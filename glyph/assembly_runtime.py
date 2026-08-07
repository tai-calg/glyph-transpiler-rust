from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
import sys
from threading import Lock
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
StateCloner = Callable[[object], object]


_BOOL_TYPES = {"B", "Bool", "bool"}
_INT_TYPES = {
    "I",
    "Int",
    "Integer",
    "i8",
    "i16",
    "i32",
    "i64",
    "i128",
    "isize",
    "u8",
    "u16",
    "u32",
    "u64",
    "u128",
    "usize",
}
_INT_RANGES: dict[str, tuple[int, int]] = {
    "i8": (-(2**7), 2**7 - 1),
    "i16": (-(2**15), 2**15 - 1),
    "i32": (-(2**31), 2**31 - 1),
    "i64": (-(2**63), 2**63 - 1),
    "i128": (-(2**127), 2**127 - 1),
    "isize": (-sys.maxsize - 1, sys.maxsize),
    "u8": (0, 2**8 - 1),
    "u16": (0, 2**16 - 1),
    "u32": (0, 2**32 - 1),
    "u64": (0, 2**64 - 1),
    "u128": (0, 2**128 - 1),
    "usize": (0, 2 * sys.maxsize + 1),
}
_FLOAT_TYPES = {"F", "Float", "f32", "f64"}
_FLOAT_MAX = {
    "f32": 3.4028234663852886e38,
    "f64": 1.7976931348623157e308,
}
_STRING_TYPES = {"String", "str"}


class ImmediateAssemblyRuntime:
    """Stateful reference executor for Assembly v1 immediate propagation.

    State and routed values use copy-by-value semantics through `state_cloner`
    (deepcopy by default). The complete top-level causal reaction commits only on
    success. Host effects remain externally observable and cannot be rolled back.
    """

    def __init__(
        self,
        ir: MachineAssemblyIR,
        initial_states: Mapping[str, object],
        *,
        state_cloner: StateCloner = deepcopy,
    ) -> None:
        expected_contract = {
            "schema": "glyph.machine-assembly-ir",
            "version": 2,
            "delivery": "immediate-call-point",
            "state_commit": "atomic-per-top-level-reaction",
            "reentrant_reaction": "forbidden",
        }
        actual_contract = {
            "schema": ir.schema,
            "version": ir.version,
            "delivery": ir.delivery,
            "state_commit": ir.state_commit,
            "reentrant_reaction": ir.reentrant_reaction,
        }
        if actual_contract != expected_contract:
            differences = ", ".join(
                f"{key}={actual_contract[key]!r} (expected {value!r})"
                for key, value in expected_contract.items()
                if actual_contract[key] != value
            )
            raise GlyphError(
                "ImmediateAssemblyRuntimeが未対応のAssembly IR契約を受け取った: "
                + differences
            )

        self.ir = ir
        self._state_cloner = state_cloner
        self._reaction_gate = Lock()
        self._instances = {
            str(item["name"]): item
            for item in ir.instances
        }
        self._types = {
            str(item["name"]): item
            for item in ir.types
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

        for instance, value in initial_states.items():
            self._validate_value(
                self._state_type(instance),
                value,
                f"initial state {instance}",
            )
        cloned = self._clone(dict(initial_states), "initial Assembly state")
        if not isinstance(cloned, dict):
            raise GlyphError("state_clonerはAssembly stateのdictを保持する必要がある")
        self._states = cloned

        self._routes: dict[tuple[str, str], Mapping[str, object]] = {}
        for route in ir.routes:
            key = (str(route["source_instance"]), str(route["effect"]))
            if key in self._routes:
                raise GlyphError(
                    f"assembly IRに重複routeがある: {key[0]}.{key[1]}"
                )
            self._routes[key] = route

    def _clone(self, value: object, context: str) -> object:
        try:
            return self._state_cloner(value)
        except Exception as exc:
            raise GlyphError(f"{context}を安全に複製できない: {exc}") from exc

    @property
    def states(self) -> dict[str, object]:
        cloned = self._clone(self._states, "Assembly state snapshot")
        if not isinstance(cloned, dict):
            raise GlyphError("state_clonerはAssembly stateのdictを保持する必要がある")
        return cloned

    def _input_records(self, instance: str) -> tuple[Mapping[str, object], ...]:
        raw = self._instances[instance].get("inputs", ())
        return tuple(item for item in raw if isinstance(item, Mapping))

    def _input_record(self, instance: str, name: str) -> Mapping[str, object] | None:
        return next(
            (
                item
                for item in self._input_records(instance)
                if str(item.get("name")) == name
            ),
            None,
        )

    def _input_names(self, instance: str) -> set[str]:
        return {str(item["name"]) for item in self._input_records(instance)}

    def _effect_records(self, instance: str) -> tuple[Mapping[str, object], ...]:
        raw = self._instances[instance].get("effects", ())
        return tuple(item for item in raw if isinstance(item, Mapping))

    def _effect_record(
        self,
        instance: str,
        name: str,
    ) -> Mapping[str, object] | None:
        return next(
            (
                item
                for item in self._effect_records(instance)
                if str(item.get("name")) == name
            ),
            None,
        )

    def _state_type(self, instance: str) -> Mapping[str, object]:
        state = self._instances[instance].get("state")
        if not isinstance(state, Mapping) or not isinstance(state.get("type_ref"), Mapping):
            raise GlyphError(f"instance '{instance}' のstate型IRが壊れている")
        return state["type_ref"]

    @staticmethod
    def _type_arguments(type_ref: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
        raw = type_ref.get("arguments", ())
        return tuple(item for item in raw if isinstance(item, Mapping))

    def _validate_value(
        self,
        type_ref: Mapping[str, object],
        value: object,
        path: str,
        alias_stack: tuple[str, ...] = (),
    ) -> None:
        name = str(type_ref.get("name") or "")
        arguments = self._type_arguments(type_ref)

        definition = self._types.get(name)
        if definition is not None and str(definition.get("kind")) == "alias":
            if name in alias_stack:
                raise GlyphError(f"{path}: 型alias循環がある: {' -> '.join((*alias_stack, name))}")
            target = definition.get("target")
            if not isinstance(target, Mapping):
                raise GlyphError(f"{path}: alias '{name}' の型IRが壊れている")
            self._validate_value(target, value, path, (*alias_stack, name))
            return

        if name == "()":
            if value is not None:
                raise GlyphError(f"{path}: ()にはNoneが必要")
            return
        if name in _BOOL_TYPES:
            if type(value) is not bool:
                raise GlyphError(f"{path}: {name}にはboolが必要")
            return
        if name in _INT_TYPES:
            if type(value) is not int:
                raise GlyphError(f"{path}: {name}にはintが必要")
            bounds = _INT_RANGES.get(name)
            if bounds is not None and not bounds[0] <= value <= bounds[1]:
                raise GlyphError(
                    f"{path}: {name}の範囲外: {value} "
                    f"(許容範囲 {bounds[0]}..{bounds[1]})"
                )
            return
        if name in _FLOAT_TYPES:
            if type(value) not in {int, float}:
                raise GlyphError(f"{path}: {name}には数値が必要")
            try:
                numeric = float(value)
            except (OverflowError, ValueError) as exc:
                raise GlyphError(f"{path}: {name}へ変換できない数値") from exc
            if not math.isfinite(numeric):
                raise GlyphError(f"{path}: {name}には有限値が必要")
            maximum = _FLOAT_MAX.get(name)
            if maximum is not None and abs(numeric) > maximum:
                raise GlyphError(
                    f"{path}: {name}の表現範囲外: {value} "
                    f"(最大絶対値 {maximum})"
                )
            return
        if name in _STRING_TYPES:
            if not isinstance(value, str):
                raise GlyphError(f"{path}: {name}にはstrが必要")
            return
        if name == "Option":
            if len(arguments) != 1:
                raise GlyphError(f"{path}: Option型IRの引数数が不正")
            if value is None:
                return
            if (
                isinstance(value, (tuple, list))
                and len(value) == 2
                and value[0] == "Some"
            ):
                self._validate_value(arguments[0], value[1], f"{path}.Some")
                return
            self._validate_value(arguments[0], value, f"{path}.Some")
            return
        if name == "Vec":
            if len(arguments) != 1 or not isinstance(value, (tuple, list)):
                raise GlyphError(f"{path}: Vec<T>にはsequenceが必要")
            for index, item in enumerate(value):
                self._validate_value(arguments[0], item, f"{path}[{index}]")
            return
        if name == "Tuple":
            if not isinstance(value, (tuple, list)) or len(value) != len(arguments):
                raise GlyphError(f"{path}: Tupleの要素数が型と一致しない")
            for index, (item_type, item) in enumerate(zip(arguments, value)):
                self._validate_value(item_type, item, f"{path}[{index}]")
            return
        if name == "Result":
            if len(arguments) != 2 or not isinstance(value, (tuple, list)) or len(value) != 2:
                raise GlyphError(f"{path}: Result<T,E>には('Ok',value)または('Err',error)が必要")
            tag = value[0]
            if tag == "Ok":
                self._validate_value(arguments[0], value[1], f"{path}.Ok")
                return
            if tag == "Err":
                self._validate_value(arguments[1], value[1], f"{path}.Err")
                return
            raise GlyphError(f"{path}: Result tagはOkまたはErrが必要")

        if definition is not None and str(definition.get("kind")) == "product":
            fields = tuple(
                item
                for item in definition.get("fields", ())
                if isinstance(item, Mapping)
            )
            if not isinstance(value, Mapping):
                raise GlyphError(f"{path}: product型 '{name}' にはmappingが必要")
            expected = {str(item["name"]) for item in fields}
            actual = {str(item) for item in value.keys()}
            if actual != expected:
                raise GlyphError(
                    f"{path}: product型 '{name}' のfieldsが不一致 "
                    f"expected={sorted(expected)} actual={sorted(actual)}"
                )
            for field in fields:
                field_name = str(field["name"])
                field_type = field.get("type")
                if not isinstance(field_type, Mapping):
                    raise GlyphError(f"{path}.{field_name}: 型IRが壊れている")
                self._validate_value(field_type, value[field_name], f"{path}.{field_name}")
            return

        if definition is not None and str(definition.get("kind")) == "sum":
            variants = {
                str(item["name"]): item
                for item in definition.get("variants", ())
                if isinstance(item, Mapping)
            }
            if isinstance(value, str):
                variant = variants.get(value)
                if variant is None:
                    raise GlyphError(f"{path}: '{value}' は{name}のvariantではない")
                if variant.get("tuple_types") or variant.get("fields"):
                    raise GlyphError(f"{path}: variant '{value}' のpayloadが不足している")
                return
            if isinstance(value, (tuple, list)) and value:
                variant_name = str(value[0])
                variant = variants.get(variant_name)
                if variant is None:
                    raise GlyphError(f"{path}: '{variant_name}' は{name}のvariantではない")
                tuple_types = tuple(
                    item for item in variant.get("tuple_types", ()) if isinstance(item, Mapping)
                )
                if variant.get("fields") or len(value) != len(tuple_types) + 1:
                    raise GlyphError(f"{path}: variant '{variant_name}' のtuple payloadが不正")
                for index, (item_type, item) in enumerate(zip(tuple_types, value[1:])):
                    self._validate_value(item_type, item, f"{path}.{variant_name}[{index}]")
                return
            if isinstance(value, Mapping) and "$variant" in value:
                variant_name = str(value["$variant"])
                variant = variants.get(variant_name)
                if variant is None:
                    raise GlyphError(f"{path}: '{variant_name}' は{name}のvariantではない")
                fields = tuple(
                    item for item in variant.get("fields", ()) if isinstance(item, Mapping)
                )
                expected = {"$variant", *(str(item["name"]) for item in fields)}
                actual = {str(item) for item in value.keys()}
                if variant.get("tuple_types") or actual != expected:
                    raise GlyphError(f"{path}: variant '{variant_name}' のrecord payloadが不正")
                for field in fields:
                    field_name = str(field["name"])
                    field_type = field.get("type")
                    if not isinstance(field_type, Mapping):
                        raise GlyphError(f"{path}.{field_name}: 型IRが壊れている")
                    self._validate_value(
                        field_type,
                        value[field_name],
                        f"{path}.{variant_name}.{field_name}",
                    )
                return
            raise GlyphError(f"{path}: sum型 '{name}' のruntime表現が不正")

        if isinstance(value, Mapping) and value.get("$type") == name:
            return
        if type(value).__name__ == name:
            return
        raise GlyphError(
            f"{path}: 未定義nominal型 '{name}' は同名classまたは{{$type:'{name}'}}が必要"
        )

    def react(
        self,
        instance: str,
        input_name: str,
        value: object,
        handler: ReactionHandler,
        host_executor: HostExecutor | None = None,
    ) -> ImmediateReactionResult:
        # Reject same-thread and cross-thread competing reactions without waiting.
        # Blocking here can deadlock when a Host callback joins the competing thread.
        if not self._reaction_gate.acquire(blocking=False):
            raise GlyphError(
                "同一Assembly Runtimeへのtop-level反応の再入は禁止（並行実行も禁止）"
            )
        try:
            return self._react_locked(
                instance,
                input_name,
                value,
                handler,
                host_executor,
            )
        finally:
            self._reaction_gate.release()

    def _react_locked(
        self,
        instance: str,
        input_name: str,
        value: object,
        handler: ReactionHandler,
        host_executor: HostExecutor | None = None,
    ) -> ImmediateReactionResult:
        if instance not in self._instances:
            raise GlyphError(f"assembly instance '{instance}' が存在しない")
        input_record = self._input_record(instance, input_name)
        if input_record is None:
            available = ", ".join(sorted(self._input_names(instance))) or "<none>"
            raise GlyphError(
                f"instance '{instance}' に入力 '{input_name}' がない。使用可能: {available}"
            )
        input_type = input_record.get("type_ref")
        if not isinstance(input_type, Mapping):
            raise GlyphError(f"instance '{instance}' の入力 '{input_name}' の型IRが壊れている")
        self._validate_value(input_type, value, f"input {instance}.{input_name}")

        working_value = self._clone(self._states, "reaction working state")
        if not isinstance(working_value, dict):
            raise GlyphError("state_clonerはAssembly stateのdictを保持する必要がある")
        working: dict[str, object] = working_value
        trace: list[ReactionTraceEntry] = []
        external: list[ExternalEffect] = []
        active: list[str] = []

        def invoke(target: str, target_input: str, payload: object) -> None:
            if target in active:
                chain = " -> ".join((*active, target))
                raise GlyphError(f"即時Machine反応の再入は禁止: {chain}")
            if target not in self._instances:
                raise GlyphError(f"assembly instance '{target}' が存在しない")
            target_input_record = self._input_record(target, target_input)
            if target_input_record is None:
                raise GlyphError(
                    f"instance '{target}' に入力 '{target_input}' がない"
                )
            target_input_type = target_input_record.get("type_ref")
            if not isinstance(target_input_type, Mapping):
                raise GlyphError(f"instance '{target}' の入力型IRが壊れている")
            self._validate_value(
                target_input_type,
                payload,
                f"input {target}.{target_input}",
            )

            active.append(target)
            depth = len(active) - 1
            before = working[target]
            trace.append(
                ReactionTraceEntry(
                    phase="enter",
                    instance=target,
                    input=target_input,
                    value=self._clone(payload, f"trace payload {target}"),
                    depth=depth,
                    state=self._clone(before, f"trace state {target}"),
                )
            )
            reaction: GeneratorType | None = None
            try:
                reaction_value = handler(target, target_input, payload, before)
                if not isinstance(reaction_value, GeneratorType):
                    raise GlyphError(
                        "Assembly reaction handlerはEffectInvocationをyieldし、"
                        "next stateをreturnするgeneratorである必要がある"
                    )
                reaction = reaction_value

                try:
                    invocation = next(reaction)
                    while True:
                        if not isinstance(invocation, EffectInvocation):
                            raise GlyphError(
                                f"instance '{target}' のreactionが"
                                "EffectInvocation以外をyieldした"
                            )
                        signature = self._effect_record(target, invocation.effect)
                        if signature is None:
                            raise GlyphError(
                                f"effect '{invocation.effect}' はMachine instance "
                                f"'{target}' の遷移Actionとして宣言されていない"
                            )
                        parameters = tuple(
                            item
                            for item in signature.get("parameters", ())
                            if isinstance(item, Mapping)
                        )
                        if len(parameters) != len(invocation.arguments):
                            raise GlyphError(
                                f"effect '{target}.{invocation.effect}' の引数数が不一致: "
                                f"expected={len(parameters)} actual={len(invocation.arguments)}"
                            )
                        for parameter, argument in zip(parameters, invocation.arguments):
                            parameter_type = parameter.get("type_ref")
                            if not isinstance(parameter_type, Mapping):
                                raise GlyphError(
                                    f"effect '{target}.{invocation.effect}' の引数型IRが壊れている"
                                )
                            self._validate_value(
                                parameter_type,
                                argument,
                                f"effect {target}.{invocation.effect}.{parameter.get('name')}",
                            )

                        route = self._routes.get((target, invocation.effect))
                        if route is not None:
                            if len(invocation.arguments) != 1:
                                raise GlyphError(
                                    f"内部route effect '{target}.{invocation.effect}' は"
                                    "payload引数を1つ必要とする"
                                )
                            routed_payload = self._clone(
                                invocation.arguments[0],
                                f"route payload {target}.{invocation.effect}",
                            )
                            invoke(
                                str(route["target_instance"]),
                                str(route["input"]),
                                routed_payload,
                            )
                            effect_result: object = None
                        else:
                            if host_executor is None:
                                raise GlyphError(
                                    f"外部effect '{target}.{invocation.effect}' を"
                                    "実行するHost executorがない"
                                )
                            host_arguments = tuple(
                                self._clone(
                                    argument,
                                    f"Host argument {target}.{invocation.effect}",
                                )
                                for argument in invocation.arguments
                            )
                            audit_arguments = tuple(
                                self._clone(
                                    argument,
                                    f"Host audit argument {target}.{invocation.effect}",
                                )
                                for argument in host_arguments
                            )
                            raw_result = host_executor(
                                target,
                                invocation.effect,
                                host_arguments,
                            )
                            result_type = signature.get("result_type_ref")
                            if not isinstance(result_type, Mapping):
                                raise GlyphError(
                                    f"effect '{target}.{invocation.effect}' の戻り値型IRが壊れている"
                                )
                            self._validate_value(
                                result_type,
                                raw_result,
                                f"Host result {target}.{invocation.effect}",
                            )
                            effect_result = self._clone(
                                raw_result,
                                f"Host result {target}.{invocation.effect}",
                            )
                            external.append(
                                ExternalEffect(
                                    instance=target,
                                    effect=invocation.effect,
                                    arguments=audit_arguments,
                                    result=self._clone(
                                        raw_result,
                                        "external effect result",
                                    ),
                                )
                            )
                        invocation = reaction.send(effect_result)
                except StopIteration as completed:
                    next_state = completed.value

                self._validate_value(
                    self._state_type(target),
                    next_state,
                    f"next state {target}",
                )
                working[target] = self._clone(next_state, f"next state {target}")
                trace.append(
                    ReactionTraceEntry(
                        phase="commit",
                        instance=target,
                        input=target_input,
                        value=self._clone(payload, f"trace payload {target}"),
                        depth=depth,
                        state=self._clone(next_state, f"trace next state {target}"),
                    )
                )
            finally:
                pending_exception = sys.exc_info()[0] is not None
                close_error: BaseException | None = None
                if reaction is not None:
                    try:
                        reaction.close()
                    except BaseException as exc:
                        close_error = exc
                active.pop()
                if close_error is not None and not pending_exception:
                    raise close_error

        top_payload = self._clone(value, f"input {instance}.{input_name}")
        invoke(instance, input_name, top_payload)
        committed = self._clone(working, "committed Assembly state")
        if not isinstance(committed, dict):
            raise GlyphError("state_clonerはAssembly stateのdictを保持する必要がある")
        self._states = committed
        return ImmediateReactionResult(
            trace=tuple(trace),
            external_effects=tuple(external),
            states=self.states,
        )

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import math
import sys
from threading import Lock
from types import GeneratorType, MappingProxyType
from typing import Callable, Generator, Mapping, Sequence

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
class FrozenObjectSnapshot:
    """Immutable audit representation for a non-container Python object."""

    type_name: str
    attributes: Mapping[str, object]


@dataclass(frozen=True)
class FrozenCycleReference:
    """Marks a cycle encountered while freezing an audit value."""

    type_name: str


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
    status: str = "validated"
    error: str | None = None


@dataclass(frozen=True)
class ImmediateReactionResult:
    trace: tuple[ReactionTraceEntry, ...]
    external_effects: tuple[ExternalEffect, ...]
    states: Mapping[str, object]


@dataclass(frozen=True)
class ImmediateReactionFailureAudit:
    trace: tuple[ReactionTraceEntry, ...]
    external_effects: tuple[ExternalEffect, ...]
    committed_states: Mapping[str, object]
    working_states: Mapping[str, object]


class ImmediateReactionFailure(GlyphError):
    """Fallback wrapper when the original exception cannot carry audit metadata."""

    def __init__(self, cause: BaseException, audit: ImmediateReactionFailureAudit):
        super().__init__(f"Assembly reaction failed: {_error_text(cause)}")
        self.cause = cause
        self.audit = audit


ReactionGenerator = Generator[EffectInvocation, object, object]
ReactionHandler = Callable[[str, str, object, object], ReactionGenerator]
HostExecutor = Callable[[str, str, tuple[object, ...]], object]


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
_PRIMITIVE_TYPE_NAMES = (
    _BOOL_TYPES | _INT_TYPES | _FLOAT_TYPES | _STRING_TYPES | {"()"}
)
_GENERIC_ARITY = {"Option": 1, "Vec": 1, "Result": 2}


def _error_text(error: BaseException) -> str:
    try:
        message = str(error)
    except BaseException:
        message = "<message unavailable>"
    try:
        type_name = type(error).__name__
    except BaseException:
        type_name = "<unknown exception>"
    return f"{type_name}: {message}"


def _public_snapshot_impl(value: object, active: set[int] | None = None) -> object:
    """Create a recursively immutable, detached audit snapshot."""

    if value is None or type(value) in {bool, int, float, str, bytes}:
        return value
    if isinstance(value, Enum):
        return value

    active = set() if active is None else active
    identity = id(value)
    if identity in active:
        return FrozenCycleReference(type(value).__qualname__)

    if isinstance(value, Mapping):
        active.add(identity)
        try:
            frozen: dict[object, object] = {}
            for key, item in value.items():
                if type(key) not in {bool, int, float, str, bytes, tuple}:
                    raise GlyphError(
                        "監査snapshotのmapping keyは不変なscalar/tupleである必要がある"
                    )
                frozen_key = _public_snapshot(key, active)
                try:
                    hash(frozen_key)
                except TypeError as exc:
                    raise GlyphError("監査snapshotのmapping keyがhashableではない") from exc
                frozen[frozen_key] = _public_snapshot(item, active)
            return MappingProxyType(frozen)
        finally:
            active.remove(identity)

    if isinstance(value, (tuple, list)):
        active.add(identity)
        try:
            return tuple(_public_snapshot(item, active) for item in value)
        finally:
            active.remove(identity)

    if isinstance(value, (set, frozenset)):
        active.add(identity)
        try:
            return frozenset(_public_snapshot(item, active) for item in value)
        finally:
            active.remove(identity)

    attributes: dict[str, object] = {}
    if is_dataclass(value) and not isinstance(value, type):
        active.add(identity)
        try:
            attributes = {
                field.name: _public_snapshot(getattr(value, field.name), active)
                for field in fields(value)
            }
        finally:
            active.remove(identity)
    elif hasattr(value, "__dict__"):
        active.add(identity)
        try:
            attributes = {
                str(name): _public_snapshot(item, active)
                for name, item in vars(value).items()
            }
        finally:
            active.remove(identity)
    else:
        slot_names: list[str] = []
        for owner in type(value).__mro__:
            raw_slots = getattr(owner, "__slots__", ())
            if isinstance(raw_slots, str):
                slot_names.append(raw_slots)
            else:
                slot_names.extend(str(name) for name in raw_slots)
        if slot_names:
            active.add(identity)
            try:
                attributes = {
                    name: _public_snapshot(getattr(value, name), active)
                    for name in slot_names
                    if name not in {"__dict__", "__weakref__"}
                    and hasattr(value, name)
                }
            finally:
                active.remove(identity)
        else:
            attributes = {"$repr": repr(value)}

    return FrozenObjectSnapshot(
        type_name=f"{type(value).__module__}.{type(value).__qualname__}",
        attributes=MappingProxyType(attributes),
    )


def _public_snapshot(value: object, active: set[int] | None = None) -> object:
    """Create a detached immutable audit snapshot without masking execution errors."""

    try:
        return _public_snapshot_impl(value, active)
    except BaseException as snapshot_error:
        try:
            type_name = f"{type(value).__module__}.{type(value).__qualname__}"
        except BaseException:
            type_name = "<unknown value>"
        return FrozenObjectSnapshot(
            type_name=type_name,
            attributes=MappingProxyType(
                {"$snapshot_error": _error_text(snapshot_error)}
            ),
        )


class ImmediateAssemblyRuntime:
    """Stateful reference executor for Assembly v1 immediate propagation.

    Internal state and routed values are structurally cloned from validated Glyph
    type metadata and never invoke Python copy protocols. The complete top-level
    causal reaction commits only on success. Host effects remain externally
    observable and are attached to failure audit metadata.
    """

    def __init__(
        self,
        ir: MachineAssemblyIR,
        initial_states: Mapping[str, object],
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
        self._reaction_gate = Lock()
        self._types = self._index_named_records(ir.types, "type")
        self._instances = self._index_named_records(ir.instances, "instance")
        self._validate_ir_integrity(ir)

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
        self._states = self._clone_state_map(
            initial_states, "initial Assembly state"
        )

        self._routes: dict[tuple[str, str], Mapping[str, object]] = {}
        for route in ir.routes:
            key = (str(route["source_instance"]), str(route["effect"]))
            self._routes[key] = route

    @staticmethod
    def _index_named_records(
        records: Sequence[Mapping[str, object]],
        kind: str,
    ) -> dict[str, Mapping[str, object]]:
        result: dict[str, Mapping[str, object]] = {}
        for index, item in enumerate(records):
            if not isinstance(item, Mapping):
                raise GlyphError(f"Assembly IR {kind}[{index}] はmappingが必要")
            name = item.get("name")
            if not isinstance(name, str) or not name:
                raise GlyphError(f"Assembly IR {kind}[{index}].name は非空文字列が必要")
            if name in result:
                raise GlyphError(f"Assembly IRに重複{kind}名がある: {name}")
            result[name] = item
        return result

    @staticmethod
    def _sequence(value: object, path: str) -> tuple[object, ...]:
        if not isinstance(value, (tuple, list)):
            raise GlyphError(f"{path} はsequenceが必要")
        return tuple(value)

    @staticmethod
    def _required_string(record: Mapping[str, object], key: str, path: str) -> str:
        value = record.get(key)
        if not isinstance(value, str) or not value:
            raise GlyphError(f"{path}.{key} は非空文字列が必要")
        return value

    def _validate_type_ref_structure(
        self,
        type_ref: object,
        path: str,
    ) -> Mapping[str, object]:
        if not isinstance(type_ref, Mapping):
            raise GlyphError(f"{path} は型mappingが必要")
        name = self._required_string(type_ref, "name", path)
        arguments = self._sequence(type_ref.get("arguments", ()), f"{path}.arguments")
        for index, argument in enumerate(arguments):
            self._validate_type_ref_structure(argument, f"{path}.arguments[{index}]")

        if name in _PRIMITIVE_TYPE_NAMES and arguments:
            raise GlyphError(f"{path}: primitive型 '{name}' は型引数を持てない")
        if name in _GENERIC_ARITY and len(arguments) != _GENERIC_ARITY[name]:
            raise GlyphError(
                f"{path}: {name}の型引数数が不正: "
                f"expected={_GENERIC_ARITY[name]} actual={len(arguments)}"
            )
        if name == "Tuple":
            return type_ref
        if name not in _PRIMITIVE_TYPE_NAMES and name not in _GENERIC_ARITY:
            if name not in self._types:
                raise GlyphError(f"{path}: 未定義型 '{name}'")
            if arguments:
                raise GlyphError(f"{path}: nominal型 '{name}' は型引数を持てない")
        return type_ref

    def _type_key(
        self,
        type_ref: Mapping[str, object],
        alias_stack: tuple[str, ...] = (),
    ) -> tuple[object, ...]:
        name = str(type_ref.get("name") or "")
        definition = self._types.get(name)
        if definition is not None and definition.get("kind") == "alias":
            if name in alias_stack:
                raise GlyphError(
                    "型alias循環がある: " + " -> ".join((*alias_stack, name))
                )
            target = definition.get("target")
            target_ref = self._validate_type_ref_structure(
                target,
                f"type {name}.target",
            )
            return self._type_key(target_ref, (*alias_stack, name))
        arguments = self._type_arguments(type_ref)
        return (name, tuple(self._type_key(item, alias_stack) for item in arguments))

    def _validate_type_definitions(self) -> None:
        reserved_type_names = _PRIMITIVE_TYPE_NAMES | set(_GENERIC_ARITY) | {"Tuple"}
        for name, definition in self._types.items():
            path = f"type {name}"
            if name in reserved_type_names:
                raise GlyphError(f"{path}: 予約型名はユーザー定義できない")
            kind = definition.get("kind")
            if kind == "alias":
                target = self._validate_type_ref_structure(
                    definition.get("target"),
                    f"{path}.target",
                )
                self._type_key(target)
                continue
            if kind == "product":
                fields_value = self._sequence(definition.get("fields", ()), f"{path}.fields")
                seen: set[str] = set()
                for index, raw_field in enumerate(fields_value):
                    if not isinstance(raw_field, Mapping):
                        raise GlyphError(f"{path}.fields[{index}] はmappingが必要")
                    field_name = self._required_string(raw_field, "name", f"{path}.fields[{index}]")
                    if field_name in seen:
                        raise GlyphError(f"{path}に重複fieldがある: {field_name}")
                    seen.add(field_name)
                    self._validate_type_ref_structure(
                        raw_field.get("type"),
                        f"{path}.fields[{index}].type",
                    )
                continue
            if kind == "sum":
                variants_value = self._sequence(
                    definition.get("variants", ()),
                    f"{path}.variants",
                )
                seen_variants: set[str] = set()
                for index, raw_variant in enumerate(variants_value):
                    if not isinstance(raw_variant, Mapping):
                        raise GlyphError(f"{path}.variants[{index}] はmappingが必要")
                    variant_path = f"{path}.variants[{index}]"
                    variant_name = self._required_string(raw_variant, "name", variant_path)
                    if variant_name in seen_variants:
                        raise GlyphError(f"{path}に重複variantがある: {variant_name}")
                    seen_variants.add(variant_name)
                    tuple_types = self._sequence(
                        raw_variant.get("tuple_types", ()),
                        f"{variant_path}.tuple_types",
                    )
                    fields_value = self._sequence(
                        raw_variant.get("fields", ()),
                        f"{variant_path}.fields",
                    )
                    if tuple_types and fields_value:
                        raise GlyphError(
                            f"{variant_path}はtuple payloadとrecord payloadを同時に持てない"
                        )
                    for item_index, item_type in enumerate(tuple_types):
                        self._validate_type_ref_structure(
                            item_type,
                            f"{variant_path}.tuple_types[{item_index}]",
                        )
                    seen_fields: set[str] = set()
                    for field_index, raw_field in enumerate(fields_value):
                        if not isinstance(raw_field, Mapping):
                            raise GlyphError(
                                f"{variant_path}.fields[{field_index}] はmappingが必要"
                            )
                        field_path = f"{variant_path}.fields[{field_index}]"
                        field_name = self._required_string(raw_field, "name", field_path)
                        if field_name in seen_fields:
                            raise GlyphError(
                                f"{variant_path}に重複fieldがある: {field_name}"
                            )
                        seen_fields.add(field_name)
                        self._validate_type_ref_structure(
                            raw_field.get("type"),
                            f"{field_path}.type",
                        )
                continue
            raise GlyphError(f"{path}.kind が不正: {kind!r}")

    def _validate_instance_records(self) -> None:
        for name, instance in self._instances.items():
            path = f"instance {name}"
            self._required_string(instance, "machine", path)
            state = instance.get("state")
            if not isinstance(state, Mapping):
                raise GlyphError(f"{path}.state はmappingが必要")
            self._required_string(state, "parameter", f"{path}.state")
            self._validate_type_ref_structure(
                state.get("type_ref"),
                f"{path}.state.type_ref",
            )

            inputs = self._sequence(instance.get("inputs", ()), f"{path}.inputs")
            input_names: set[str] = set()
            for index, raw_input in enumerate(inputs):
                if not isinstance(raw_input, Mapping):
                    raise GlyphError(f"{path}.inputs[{index}] はmappingが必要")
                input_path = f"{path}.inputs[{index}]"
                input_name = self._required_string(raw_input, "name", input_path)
                if input_name in input_names:
                    raise GlyphError(f"{path}に重複inputがある: {input_name}")
                input_names.add(input_name)
                self._validate_type_ref_structure(
                    raw_input.get("type_ref"),
                    f"{input_path}.type_ref",
                )

            effects = self._sequence(instance.get("effects", ()), f"{path}.effects")
            effect_names: set[str] = set()
            for index, raw_effect in enumerate(effects):
                if not isinstance(raw_effect, Mapping):
                    raise GlyphError(f"{path}.effects[{index}] はmappingが必要")
                effect_path = f"{path}.effects[{index}]"
                effect_name = self._required_string(raw_effect, "name", effect_path)
                if effect_name in effect_names:
                    raise GlyphError(f"{path}に重複effectがある: {effect_name}")
                effect_names.add(effect_name)
                parameters = self._sequence(
                    raw_effect.get("parameters", ()),
                    f"{effect_path}.parameters",
                )
                parameter_names: set[str] = set()
                for parameter_index, raw_parameter in enumerate(parameters):
                    if not isinstance(raw_parameter, Mapping):
                        raise GlyphError(
                            f"{effect_path}.parameters[{parameter_index}] はmappingが必要"
                        )
                    parameter_path = f"{effect_path}.parameters[{parameter_index}]"
                    parameter_name = self._required_string(
                        raw_parameter,
                        "name",
                        parameter_path,
                    )
                    if parameter_name in parameter_names:
                        raise GlyphError(
                            f"{effect_path}に重複parameterがある: {parameter_name}"
                        )
                    parameter_names.add(parameter_name)
                    self._validate_type_ref_structure(
                        raw_parameter.get("type_ref"),
                        f"{parameter_path}.type_ref",
                    )
                self._validate_type_ref_structure(
                    raw_effect.get("result_type_ref"),
                    f"{effect_path}.result_type_ref",
                )

            allowed = self._sequence(
                instance.get("allowed_effects", ()),
                f"{path}.allowed_effects",
            )
            allowed_names: list[str] = []
            for index, item in enumerate(allowed):
                if not isinstance(item, str) or not item:
                    raise GlyphError(
                        f"{path}.allowed_effects[{index}] は非空文字列が必要"
                    )
                allowed_names.append(item)
            if len(set(allowed_names)) != len(allowed_names):
                raise GlyphError(f"{path}.allowed_effects に重複がある")
            if set(allowed_names) != effect_names:
                raise GlyphError(
                    f"{path}.allowed_effects とeffectsが一致しない: "
                    f"allowed={sorted(allowed_names)} effects={sorted(effect_names)}"
                )

    def _validate_route_records(self, ir: MachineAssemblyIR) -> None:
        seen_sources: set[tuple[str, str]] = set()
        seen_orders: set[int] = set()
        for index, raw_route in enumerate(ir.routes):
            if not isinstance(raw_route, Mapping):
                raise GlyphError(f"route[{index}] はmappingが必要")
            path = f"route[{index}]"
            source_name = self._required_string(raw_route, "source_instance", path)
            target_name = self._required_string(raw_route, "target_instance", path)
            effect_name = self._required_string(raw_route, "effect", path)
            input_name = self._required_string(raw_route, "input", path)
            if source_name not in self._instances:
                raise GlyphError(f"{path}: source instance '{source_name}' が存在しない")
            if target_name not in self._instances:
                raise GlyphError(f"{path}: target instance '{target_name}' が存在しない")
            if source_name == target_name:
                raise GlyphError(f"{path}: v1では自己routeを許可しない")

            source_machine = raw_route.get("source_machine")
            target_machine = raw_route.get("target_machine")
            if source_machine != self._instances[source_name].get("machine"):
                raise GlyphError(f"{path}.source_machine がinstance定義と一致しない")
            if target_machine != self._instances[target_name].get("machine"):
                raise GlyphError(f"{path}.target_machine がinstance定義と一致しない")

            source_key = (source_name, effect_name)
            if source_key in seen_sources:
                raise GlyphError(
                    f"Assembly IRに重複route sourceがある: {source_name}.{effect_name}"
                )
            seen_sources.add(source_key)

            order = raw_route.get("order")
            if type(order) is not int or order <= 0:
                raise GlyphError(f"{path}.order は正の整数が必要")
            if order in seen_orders:
                raise GlyphError(f"Assembly IRに重複route orderがある: {order}")
            seen_orders.add(order)
            if raw_route.get("delivery") != "immediate":
                raise GlyphError(f"{path}.delivery は'immediate'が必要")

            effect = self._effect_record(source_name, effect_name)
            if effect is None:
                raise GlyphError(
                    f"{path}: effect '{source_name}.{effect_name}' が存在しない"
                )
            target_input = self._input_record(target_name, input_name)
            if target_input is None:
                raise GlyphError(
                    f"{path}: input '{target_name}.{input_name}' が存在しない"
                )
            parameters = tuple(
                item
                for item in self._sequence(
                    effect.get("parameters", ()),
                    f"{path}.source_effect.parameters",
                )
                if isinstance(item, Mapping)
            )
            if len(parameters) != 1:
                raise GlyphError(f"{path}: routed effectはparameterを1つ必要とする")
            payload_parameter = self._required_string(
                raw_route,
                "payload_parameter",
                path,
            )
            if payload_parameter != parameters[0].get("name"):
                raise GlyphError(f"{path}.payload_parameter がeffect定義と一致しない")

            source_type = self._validate_type_ref_structure(
                parameters[0].get("type_ref"),
                f"{path}.source_effect.parameter.type_ref",
            )
            route_payload_type = self._validate_type_ref_structure(
                raw_route.get("payload_type_ref"),
                f"{path}.payload_type_ref",
            )
            target_type = self._validate_type_ref_structure(
                target_input.get("type_ref"),
                f"{path}.target_input.type_ref",
            )
            effect_result = self._validate_type_ref_structure(
                effect.get("result_type_ref"),
                f"{path}.source_effect.result_type_ref",
            )
            route_result = self._validate_type_ref_structure(
                raw_route.get("result_type_ref"),
                f"{path}.result_type_ref",
            )
            if not (
                self._type_key(source_type)
                == self._type_key(route_payload_type)
                == self._type_key(target_type)
            ):
                raise GlyphError(f"{path}: route payload型がsource/targetと一致しない")
            unit_key = ("()", ())
            if self._type_key(effect_result) != unit_key:
                raise GlyphError(f"{path}: routed effectの戻り値はunitが必要")
            if self._type_key(route_result) != unit_key:
                raise GlyphError(f"{path}: route result型はunitが必要")

    def _validate_ir_integrity(self, ir: MachineAssemblyIR) -> None:
        self._validate_type_definitions()
        self._validate_instance_records()
        self._validate_route_records(ir)

    def _clone_typed(
        self,
        type_ref: Mapping[str, object],
        value: object,
        path: str,
        alias_stack: tuple[str, ...] = (),
    ) -> object:
        """Clone a validated Glyph value without invoking Python copy protocols."""

        name = str(type_ref.get("name") or "")
        arguments = self._type_arguments(type_ref)
        definition = self._types.get(name)
        if definition is not None and definition.get("kind") == "alias":
            if name in alias_stack:
                raise GlyphError(
                    f"{path}: 型alias循環がある: {' -> '.join((*alias_stack, name))}"
                )
            target = definition.get("target")
            if not isinstance(target, Mapping):
                raise GlyphError(f"{path}: alias '{name}' の型IRが壊れている")
            return self._clone_typed(target, value, path, (*alias_stack, name))

        if name == "()" or name in _BOOL_TYPES or name in _INT_TYPES or name in _FLOAT_TYPES:
            return value
        if name in _STRING_TYPES:
            return str(value)
        if name == "Option":
            if value is None:
                return None
            if isinstance(value, (tuple, list)) and len(value) == 2 and value[0] == "Some":
                return (
                    "Some",
                    self._clone_typed(arguments[0], value[1], f"{path}.Some"),
                )
            return self._clone_typed(arguments[0], value, f"{path}.Some")
        if name == "Vec":
            return [
                self._clone_typed(arguments[0], item, f"{path}[{index}]")
                for index, item in enumerate(value)
            ]
        if name == "Tuple":
            return tuple(
                self._clone_typed(item_type, item, f"{path}[{index}]")
                for index, (item_type, item) in enumerate(zip(arguments, value))
            )
        if name == "Result":
            tag = value[0]
            branch = 0 if tag == "Ok" else 1
            return (
                tag,
                self._clone_typed(arguments[branch], value[1], f"{path}.{tag}"),
            )

        if definition is not None and definition.get("kind") == "product":
            fields_value = tuple(
                item
                for item in definition.get("fields", ())
                if isinstance(item, Mapping)
            )
            cloned: dict[str, object] = {}
            for field in fields_value:
                field_name = str(field["name"])
                field_type = field.get("type")
                if not isinstance(field_type, Mapping):
                    raise GlyphError(f"{path}.{field_name}: 型IRが壊れている")
                cloned[field_name] = self._clone_typed(
                    field_type,
                    value[field_name],
                    f"{path}.{field_name}",
                )
            return cloned

        if definition is not None and definition.get("kind") == "sum":
            variants = {
                str(item["name"]): item
                for item in definition.get("variants", ())
                if isinstance(item, Mapping)
            }
            if isinstance(value, str):
                return str(value)
            if isinstance(value, (tuple, list)) and value:
                variant_name = str(value[0])
                variant = variants[variant_name]
                tuple_types = tuple(
                    item
                    for item in variant.get("tuple_types", ())
                    if isinstance(item, Mapping)
                )
                return (
                    variant_name,
                    *(
                        self._clone_typed(
                            item_type,
                            item,
                            f"{path}.{variant_name}[{index}]",
                        )
                        for index, (item_type, item) in enumerate(
                            zip(tuple_types, value[1:])
                        )
                    ),
                )
            if isinstance(value, Mapping) and "$variant" in value:
                variant_name = str(value["$variant"])
                variant = variants[variant_name]
                cloned_record: dict[str, object] = {"$variant": variant_name}
                for field in variant.get("fields", ()):
                    if not isinstance(field, Mapping):
                        continue
                    field_name = str(field["name"])
                    field_type = field.get("type")
                    if not isinstance(field_type, Mapping):
                        raise GlyphError(f"{path}.{field_name}: 型IRが壊れている")
                    cloned_record[field_name] = self._clone_typed(
                        field_type,
                        value[field_name],
                        f"{path}.{variant_name}.{field_name}",
                    )
                return cloned_record

        raise GlyphError(f"{path}: 型 '{name}' をstructural cloneできない")

    def _clone_state_map(
        self,
        states: Mapping[str, object],
        context: str,
    ) -> dict[str, object]:
        return {
            instance: self._clone_typed(
                self._state_type(instance),
                states[instance],
                f"{context}.{instance}",
            )
            for instance in self._instances
        }

    @property
    def states(self) -> dict[str, object]:
        return self._clone_state_map(self._states, "Assembly state snapshot")

    def _input_records(self, instance: str) -> tuple[Mapping[str, object], ...]:
        raw = self._instances[instance].get("inputs", ())
        return tuple(item for item in raw if isinstance(item, Mapping))

    def _input_record(self, instance: str, name: str) -> Mapping[str, object] | None:
        return next(
            (
                item
                for item in self._input_records(instance)
                if item.get("name") == name
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
                if item.get("name") == name
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
        if definition is not None and definition.get("kind") == "alias":
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

        if definition is not None and definition.get("kind") == "product":
            raw_fields = definition.get("fields", ())
            fields_value = tuple(
                item for item in raw_fields if isinstance(item, Mapping)
            )
            if not isinstance(value, Mapping):
                raise GlyphError(f"{path}: product型 '{name}' にはmappingが必要")
            expected = {str(item["name"]) for item in fields_value}
            actual = {str(item) for item in value.keys()}
            if actual != expected:
                raise GlyphError(
                    f"{path}: product型 '{name}' のfieldsが不一致 "
                    f"expected={sorted(expected)} actual={sorted(actual)}"
                )
            for field in fields_value:
                field_name = str(field["name"])
                field_type = field.get("type")
                if not isinstance(field_type, Mapping):
                    raise GlyphError(f"{path}.{field_name}: 型IRが壊れている")
                self._validate_value(field_type, value[field_name], f"{path}.{field_name}")
            return

        if definition is not None and definition.get("kind") == "sum":
            raw_variants = definition.get("variants", ())
            variants = {
                str(item["name"]): item
                for item in raw_variants
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
                fields_value = tuple(
                    item for item in variant.get("fields", ()) if isinstance(item, Mapping)
                )
                expected = {"$variant", *(str(item["name"]) for item in fields_value)}
                actual = {str(item) for item in value.keys()}
                if variant.get("tuple_types") or actual != expected:
                    raise GlyphError(f"{path}: variant '{variant_name}' のrecord payloadが不正")
                for field in fields_value:
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

    def _failure_audit(
        self,
        trace: list[ReactionTraceEntry],
        external: list[ExternalEffect],
        working: Mapping[str, object],
    ) -> ImmediateReactionFailureAudit:
        return ImmediateReactionFailureAudit(
            trace=tuple(trace),
            external_effects=tuple(external),
            committed_states=_public_snapshot(self._states),
            working_states=_public_snapshot(working),
        )

    @staticmethod
    def _raise_with_audit(
        error: BaseException,
        audit: ImmediateReactionFailureAudit,
    ) -> None:
        try:
            setattr(error, "assembly_audit", audit)
        except Exception:
            raise ImmediateReactionFailure(error, audit) from error
        raise error

    def react(
        self,
        instance: str,
        input_name: str,
        value: object,
        handler: ReactionHandler,
        host_executor: HostExecutor | None = None,
    ) -> ImmediateReactionResult:
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

        working: dict[str, object] = self._clone_state_map(
            self._states, "reaction working state"
        )
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
                raise GlyphError(f"instance '{target}' に入力 '{target_input}' がない")
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
                    value=_public_snapshot(payload),
                    depth=depth,
                    state=_public_snapshot(before),
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
                            payload_type = parameters[0].get("type_ref")
                            if not isinstance(payload_type, Mapping):
                                raise GlyphError(
                                    f"effect '{target}.{invocation.effect}' のpayload型IRが壊れている"
                                )
                            routed_payload = self._clone_typed(
                                payload_type,
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
                            host_arguments_list: list[object] = []
                            for parameter, argument in zip(
                                parameters, invocation.arguments
                            ):
                                parameter_type = parameter.get("type_ref")
                                if not isinstance(parameter_type, Mapping):
                                    raise GlyphError(
                                        f"effect '{target}.{invocation.effect}' の引数型IRが壊れている"
                                    )
                                host_arguments_list.append(
                                    self._clone_typed(
                                        parameter_type,
                                        argument,
                                        f"Host argument {target}.{invocation.effect}",
                                    )
                                )
                            host_arguments = tuple(host_arguments_list)
                            audit_arguments = tuple(
                                _public_snapshot(argument)
                                for argument in host_arguments
                            )
                            audit_index = len(external)
                            external.append(
                                ExternalEffect(
                                    instance=target,
                                    effect=invocation.effect,
                                    arguments=audit_arguments,
                                    result=None,
                                    status="attempted",
                                )
                            )
                            try:
                                raw_result = host_executor(
                                    target,
                                    invocation.effect,
                                    host_arguments,
                                )
                            except BaseException as host_error:
                                external[audit_index] = ExternalEffect(
                                    instance=target,
                                    effect=invocation.effect,
                                    arguments=audit_arguments,
                                    result=None,
                                    status="raised",
                                    error=_error_text(host_error),
                                )
                                raise

                            result_snapshot = _public_snapshot(raw_result)
                            result_type = signature.get("result_type_ref")
                            if not isinstance(result_type, Mapping):
                                definition_error = GlyphError(
                                    f"effect '{target}.{invocation.effect}' の戻り値型IRが壊れている"
                                )
                                external[audit_index] = ExternalEffect(
                                    instance=target,
                                    effect=invocation.effect,
                                    arguments=audit_arguments,
                                    result=result_snapshot,
                                    status="invalid-result",
                                    error=_error_text(definition_error),
                                )
                                raise definition_error
                            try:
                                self._validate_value(
                                    result_type,
                                    raw_result,
                                    f"Host result {target}.{invocation.effect}",
                                )
                            except BaseException as validation_error:
                                external[audit_index] = ExternalEffect(
                                    instance=target,
                                    effect=invocation.effect,
                                    arguments=audit_arguments,
                                    result=result_snapshot,
                                    status="invalid-result",
                                    error=_error_text(validation_error),
                                )
                                raise
                            effect_result = self._clone_typed(
                                result_type,
                                raw_result,
                                f"Host result {target}.{invocation.effect}",
                            )
                            external[audit_index] = ExternalEffect(
                                instance=target,
                                effect=invocation.effect,
                                arguments=audit_arguments,
                                result=result_snapshot,
                                status="validated",
                            )
                        invocation = reaction.send(effect_result)
                except StopIteration as completed:
                    next_state = completed.value

                self._validate_value(
                    self._state_type(target),
                    next_state,
                    f"next state {target}",
                )
                working[target] = self._clone_typed(
                    self._state_type(target),
                    next_state,
                    f"next state {target}",
                )
                trace.append(
                    ReactionTraceEntry(
                        phase="stage",
                        instance=target,
                        input=target_input,
                        value=_public_snapshot(payload),
                        depth=depth,
                        state=_public_snapshot(next_state),
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

        try:
            top_payload = self._clone_typed(
                input_type,
                value,
                f"input {instance}.{input_name}",
            )
            invoke(instance, input_name, top_payload)
            self._states = self._clone_state_map(
                working, "committed Assembly state"
            )
            return ImmediateReactionResult(
                trace=tuple(trace),
                external_effects=tuple(external),
                states=_public_snapshot(self._states),
            )
        except BaseException as error:
            self._raise_with_audit(
                error,
                self._failure_audit(trace, external, working),
            )
            raise AssertionError("unreachable")


__all__ = [
    "EffectInvocation",
    "ExternalEffect",
    "FrozenCycleReference",
    "FrozenObjectSnapshot",
    "HostExecutor",
    "ImmediateAssemblyRuntime",
    "ImmediateReactionFailure",
    "ImmediateReactionFailureAudit",
    "ImmediateReactionResult",
    "ReactionGenerator",
    "ReactionHandler",
    "ReactionTraceEntry",
]

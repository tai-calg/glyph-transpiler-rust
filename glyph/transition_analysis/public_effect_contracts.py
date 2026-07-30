from __future__ import annotations

from dataclasses import dataclass

from .abstract_store import AbstractAddress, AbstractLocation
from .abstract_value import (
    ConstantValue,
    ConstructorValue as AbstractConstructorValue,
    FieldValue,
    ParameterValue,
)
from .concrete import (
    ConstructorValue as ConcreteConstructorValue,
    VariantValue,
)
from .effect_contract import (
    VerifiedEffectContract,
    VerifiedEffectContractRegistry,
    read_only_identity_contract,
    reviewed_deterministic_contract,
)
from .effect_summary import EffectWrite


PUBLIC_STRICT_EFFECT_SURFACE_VERSION = 1
BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID = "builtin:default-workspace"


@dataclass(frozen=True)
class PublicEffectContractCase:
    contract: VerifiedEffectContract
    replay_arguments: tuple[object, ...]
    expected_result: object
    expected_external_locations: tuple[str, ...]

    @property
    def operation(self) -> str:
        return self.contract.operation

    def to_ir(self) -> dict[str, object]:
        return {
            "contract": self.contract.to_ir(),
            "replay_arguments": [repr(item) for item in self.replay_arguments],
            "expected_result": repr(self.expected_result),
            "expected_external_locations": list(
                self.expected_external_locations
            ),
        }


@dataclass(frozen=True)
class PublicStrictProgram:
    source_id: str
    system: str
    entry: str
    cases: tuple[PublicEffectContractCase, ...]
    source_path: str | None = None
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("public strict source id must not be empty")
        if not self.system.strip() or not self.entry.strip():
            raise ValueError("public strict System and entry must not be empty")
        operations = [item.operation for item in self.cases]
        if len(operations) != len(set(operations)):
            raise ValueError(
                f"duplicate public Effect operation in {self.source_id}"
            )

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(item.operation for item in self.cases)

    def registry(self) -> VerifiedEffectContractRegistry:
        return VerifiedEffectContractRegistry(
            by_entry=(
                (
                    self.entry,
                    tuple(
                        (item.operation, item.contract)
                        for item in self.cases
                    ),
                ),
            )
        )

    def to_ir(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_path": self.source_path,
            "system": self.system,
            "entry": self.entry,
            "operations": list(self.operations),
            "rationale": self.rationale,
            "contracts": [item.to_ir() for item in self.cases],
        }


@dataclass(frozen=True)
class PublicStrictExclusion:
    source_path: str
    system: str | None
    entry: str | None
    operations: tuple[str, ...]
    reason: str

    def to_ir(self) -> dict[str, object]:
        return {
            "source_path": self.source_path,
            "system": self.system,
            "entry": self.entry,
            "operations": list(self.operations),
            "reason": self.reason,
        }


def _parameter(operation: str, name: str) -> ParameterValue:
    return ParameterValue(operation, name)


def _external_write(key: str, value: object) -> EffectWrite:
    return EffectWrite(
        AbstractAddress(
            frozenset({AbstractLocation("external", key)}),
            singleton_proven=True,
        ),
        value,  # type: ignore[arg-type]
    )


def _require_arity(
    operation: str,
    arguments: tuple[object, ...],
    expected: int,
) -> None:
    if len(arguments) != expected:
        raise ValueError(
            f"public Effect {operation} expects {expected} arguments, "
            f"got {len(arguments)}"
        )


def _default_actuator_case() -> PublicEffectContractCase:
    operation = "actuator"
    state = _parameter(operation, "state")
    return_value = AbstractConstructorValue("Receipt", ("state",), (state,))

    def handler(arguments: tuple[object, ...]) -> object:
        _require_arity(operation, arguments, 1)
        return ConcreteConstructorValue("Receipt", (("state", arguments[0]),))

    sample_state = ConcreteConstructorValue(
        "DoorState",
        (("mode", VariantValue("Closed")),),
    )
    expected = ConcreteConstructorValue("Receipt", (("state", sample_state),))
    contract = reviewed_deterministic_contract(
        operation,
        ("state",),
        return_value,
        handler,
        source=(
            "public strict v1 default workspace: actuator applies exactly the "
            "requested DoorState and confirms it as Receipt(state)"
        ),
        writes=(
            _external_write("door-actuator.current-state", state),
        ),
        review_notes=(
            "No failure value is part of the default workspace declaration. "
            "The Host must update the actuator state before returning Receipt."
        ),
    )
    return PublicEffectContractCase(
        contract,
        (sample_state,),
        expected,
        ("door-actuator.current-state",),
    )


def _motor_write_case() -> PublicEffectContractCase:
    operation = "write_motor"
    command = _parameter(operation, "command")
    return_value = AbstractConstructorValue(
        "Receipt",
        ("command",),
        (command,),
    )

    def handler(arguments: tuple[object, ...]) -> object:
        _require_arity(operation, arguments, 1)
        return ConcreteConstructorValue("Receipt", (("command", arguments[0]),))

    sample_command = VariantValue("DisableMotor")
    expected = ConcreteConstructorValue(
        "Receipt",
        (("command", sample_command),),
    )
    contract = reviewed_deterministic_contract(
        operation,
        ("command",),
        return_value,
        handler,
        source=(
            "public strict v1 motor safety: write_motor commits the supplied "
            "MotorCommand and returns Receipt(command)"
        ),
        writes=(
            _external_write("motor.command", command),
        ),
        review_notes=(
            "The public Motor Safety declaration has no failure result. "
            "A Host implementation that can fail must use a different typed Effect."
        ),
    )
    return PublicEffectContractCase(
        contract,
        (sample_command,),
        expected,
        ("motor.command",),
    )


def _submit_batch_case() -> PublicEffectContractCase:
    operation = "submit_batch"
    layout = _parameter(operation, "layout")
    lane = FieldValue(layout, "lane")
    return_value = AbstractConstructorValue(
        "SubmitReceipt",
        ("lane",),
        (lane,),
    )

    def handler(arguments: tuple[object, ...]) -> object:
        _require_arity(operation, arguments, 1)
        value = arguments[0]
        if not isinstance(value, ConcreteConstructorValue):
            raise ValueError("submit_batch requires a concrete BatchLayout")
        return ConcreteConstructorValue(
            "SubmitReceipt",
            (("lane", value.field("lane")),),
        )

    sample_layout = ConcreteConstructorValue(
        "BatchLayout",
        (("lane", 2), ("size", 5)),
    )
    expected = ConcreteConstructorValue("SubmitReceipt", (("lane", 2),))
    contract = reviewed_deterministic_contract(
        operation,
        ("layout",),
        return_value,
        handler,
        source=(
            "public strict v1 batch runtime: submit_batch records the complete "
            "BatchLayout and returns SubmitReceipt(layout.lane)"
        ),
        writes=(
            _external_write("batch-runtime.last-submission", layout),
        ),
        review_notes=(
            "The public Batch Runtime declaration has no failure result. "
            "Submission rejection requires a separately typed Effect contract."
        ),
    )
    return PublicEffectContractCase(
        contract,
        (sample_layout,),
        expected,
        ("batch-runtime.last-submission",),
    )


def _door_boolean_case(
    operation: str,
    external_key: str,
) -> PublicEffectContractCase:
    command = _parameter(operation, "command")

    def handler(arguments: tuple[object, ...]) -> object:
        _require_arity(operation, arguments, 1)
        return True

    sample_command = VariantValue("Stop")
    contract = reviewed_deterministic_contract(
        operation,
        ("command",),
        ConstantValue(True),
        handler,
        source=(
            f"public strict v1 door sketch: {operation} accepts the supplied "
            "Command, records it at the declared external boundary and returns true"
        ),
        writes=(_external_write(external_key, command),),
        review_notes=(
            "The Boolean return is an acknowledgement, not a second state value. "
            "The declaration contains no failure channel."
        ),
    )
    return PublicEffectContractCase(
        contract,
        (sample_command,),
        True,
        (external_key,),
    )


def _strict_identity_case() -> PublicEffectContractCase:
    contract = read_only_identity_contract(
        "actuator",
        "state",
        source=(
            "public strict v1 acceptance: reviewed read-only identity actuator"
        ),
    )
    sample_state = ConcreteConstructorValue(
        "DoorState",
        (("mode", VariantValue("Closed")),),
    )
    return PublicEffectContractCase(contract, (sample_state,), sample_state, ())


PUBLIC_STRICT_PROGRAMS = (
    PublicStrictProgram(
        source_id=BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID,
        source_path=None,
        system="DoorControl",
        entry="control",
        cases=(_default_actuator_case(),),
        rationale=(
            "The first-run workspace is part of the public product surface and "
            "uses one deterministic actuator acknowledgement contract."
        ),
    ),
    PublicStrictProgram(
        source_id="examples/acceptance/motor_safety.glyph",
        source_path="examples/acceptance/motor_safety.glyph",
        system="MotorSafety",
        entry="cycle",
        cases=(_motor_write_case(),),
        rationale=(
            "Motor Safety is a documented acceptance example with a deterministic "
            "command/receipt boundary."
        ),
    ),
    PublicStrictProgram(
        source_id="examples/acceptance/job_scheduler.glyph",
        source_path="examples/acceptance/job_scheduler.glyph",
        system="BatchRuntime",
        entry="run",
        cases=(_submit_batch_case(),),
        rationale=(
            "Batch Runtime exposes one deterministic submission boundary after "
            "pure validation and layout."
        ),
    ),
    PublicStrictProgram(
        source_id="examples/door_sketch.glyph",
        source_path="examples/door_sketch.glyph",
        system="Door",
        entry="control",
        cases=(
            _door_boolean_case("lock", "door.lock-command"),
            _door_boolean_case("log", "door.log-command"),
        ),
        rationale=(
            "Door Sketch declares Boolean acknowledgements without a failure "
            "channel; both external writes are therefore fully specified."
        ),
    ),
    PublicStrictProgram(
        source_id="examples/acceptance/rtai_strict_projection.glyph",
        source_path="examples/acceptance/rtai_strict_projection.glyph",
        system="DoorControl",
        entry="control",
        cases=(_strict_identity_case(),),
        rationale=(
            "The strict acceptance fixture remains a read-only identity Effect so "
            "the projection campaign can isolate Evidence correctness."
        ),
    ),
)


PUBLIC_STRICT_EXCLUSIONS = (
    PublicStrictExclusion(
        source_path="examples/acceptance/door_controller.glyph",
        system="DoorController",
        entry="control",
        operations=("alarm", "lock"),
        reason=(
            "The declarations return Receipt|ControlError, but the Host contract "
            "does not specify the exact operation-specific error set or whether "
            "external state changes before each failure. Exact strict projection "
            "would therefore fabricate semantics."
        ),
    ),
    PublicStrictExclusion(
        source_path="examples/system_controller.glyph",
        system="ControllerService",
        entry="cycle",
        operations=("write_actuator",),
        reason=(
            "write_actuator returns Cycle|Error without a reviewed rule for the "
            "Actuator failure case or the failure-time external store. "
            "report_violation is not reachable from the public cycle entry."
        ),
    ),
    PublicStrictExclusion(
        source_path="examples/controller.glyph",
        system=None,
        entry=None,
        operations=("exec",),
        reason=(
            "The example has no System entry. RTAI strict projection is scoped to "
            "an explicit public System execution context."
        ),
    ),
)


def public_strict_program(source_id: str) -> PublicStrictProgram:
    for program in PUBLIC_STRICT_PROGRAMS:
        if program.source_id == source_id:
            return program
    raise KeyError(f"source is not in the public strict Effect surface: {source_id}")


def public_strict_surface_ir() -> dict[str, object]:
    return {
        "version": PUBLIC_STRICT_EFFECT_SURFACE_VERSION,
        "included": [item.to_ir() for item in PUBLIC_STRICT_PROGRAMS],
        "excluded": [item.to_ir() for item in PUBLIC_STRICT_EXCLUSIONS],
    }


__all__ = [
    "BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID",
    "PUBLIC_STRICT_EFFECT_SURFACE_VERSION",
    "PUBLIC_STRICT_EXCLUSIONS",
    "PUBLIC_STRICT_PROGRAMS",
    "PublicEffectContractCase",
    "PublicStrictExclusion",
    "PublicStrictProgram",
    "public_strict_program",
    "public_strict_surface_ir",
]

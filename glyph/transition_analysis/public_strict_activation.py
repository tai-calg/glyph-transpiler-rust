from __future__ import annotations

from dataclasses import dataclass

from ..artifacts import CompilationModel
from ..compiler import ExternDecl
from .concrete import ConstructorValue, VariantValue
from .effect_contract_audit import audit_effect_contract_coverage
from .public_effect_contracts import (
    BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID,
    PUBLIC_STRICT_EFFECT_SURFACE_VERSION,
    PUBLIC_STRICT_PROGRAMS,
    PublicStrictProgram,
)
from .witness_generation import (
    TargetedWitnessCase,
    TargetedWitnessRegistry,
)


PUBLIC_STRICT_ACTIVATION_VERSION = 1


@dataclass(frozen=True)
class PublicStrictActivation:
    program: PublicStrictProgram
    targeted_witnesses: TargetedWitnessRegistry | None = None

    def to_ir(self) -> dict[str, object]:
        return {
            "version": PUBLIC_STRICT_ACTIVATION_VERSION,
            "active": True,
            "surface_version": PUBLIC_STRICT_EFFECT_SURFACE_VERSION,
            "source_id": self.program.source_id,
            "system": self.program.system,
            "entry": self.program.entry,
            "operations": list(self.program.operations),
            "targeted_witness_case_count": (
                len(self.targeted_witnesses.cases)
                if self.targeted_witnesses is not None
                else 0
            ),
        }


def inactive_public_strict_activation_ir(reason: str) -> dict[str, object]:
    return {
        "version": PUBLIC_STRICT_ACTIVATION_VERSION,
        "active": False,
        "surface_version": PUBLIC_STRICT_EFFECT_SURFACE_VERSION,
        "source_id": None,
        "system": None,
        "entry": None,
        "operations": [],
        "targeted_witness_case_count": 0,
        "reason": reason,
    }


def select_public_strict_activation(
    model: CompilationModel,
    source_name: str,
) -> PublicStrictActivation | None:
    """Select strict-exact only for a reviewed public context.

    A path match alone is insufficient. The compiled System name, entry, reachable
    outbound Effect set, contract coverage and declaration parameter order must all
    still match the reviewed catalog. Any mismatch leaves the normal application in
    shadow mode rather than guessing that an edited source remains compatible.
    """

    for program in PUBLIC_STRICT_PROGRAMS:
        if not _source_matches(program, source_name):
            continue
        if not _system_matches(model, program):
            continue
        report = audit_effect_contract_coverage(
            model,
            (program.entry,),
            program.registry(),
        )
        if not report.complete or len(report.entries) != 1:
            continue
        if set(report.entries[0].required_operations) != set(program.operations):
            continue
        if not _contract_parameters_match(model, program):
            continue
        return PublicStrictActivation(
            program,
            targeted_witnesses=_targeted_witnesses(program),
        )
    return None


def _source_matches(program: PublicStrictProgram, source_name: str) -> bool:
    normalized = source_name.replace("\\", "/").rstrip("/")
    if program.source_id == BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID:
        return normalized == program.source_id or normalized.endswith(
            "/.glyph/workspace.glyph"
        ) or normalized == ".glyph/workspace.glyph"
    path = str(program.source_path or "").replace("\\", "/").lstrip("/")
    return bool(path) and (normalized == path or normalized.endswith("/" + path))


def _system_matches(model: CompilationModel, program: PublicStrictProgram) -> bool:
    return any(
        system.name == program.system and system.entry_name == program.entry
        for system in model.systems
    )


def _contract_parameters_match(
    model: CompilationModel,
    program: PublicStrictProgram,
) -> bool:
    declarations = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, ExternDecl)
    }
    for case in program.cases:
        declaration = declarations.get(case.operation)
        if declaration is None:
            return False
        if case.contract.summary.parameters != tuple(
            parameter.name for parameter in declaration.params
        ):
            return False
    return True


def _targeted_witnesses(
    program: PublicStrictProgram,
) -> TargetedWitnessRegistry | None:
    if program.source_id != "examples/acceptance/motor_safety.glyph":
        return None

    disable = VariantValue("DisableMotor")
    stopped = VariantValue("Stopped")
    receipt = ConstructorValue("Receipt", (("command", disable),))
    state = ConstructorValue(
        "MotorState",
        (
            ("mode", stopped),
            ("command", disable),
            ("receipt", receipt),
        ),
    )

    def input_value(
        raw: float,
        enabled: bool,
        emergency: bool,
        fault: bool,
        stopped_value: bool,
    ) -> ConstructorValue:
        return ConstructorValue(
            "Input",
            (
                ("raw", raw),
                ("enabled", enabled),
                ("emergency", emergency),
                ("fault", fault),
                ("stopped", stopped_value),
            ),
        )

    source = "public strict v1 motor edge witness"
    return TargetedWitnessRegistry(
        cases=(
            TargetedWitnessCase(
                program.entry,
                (state, input_value(0.0, True, False, True, False)),
                source,
                "fault-latch",
            ),
            TargetedWitnessCase(
                program.entry,
                (state, input_value(0.0, True, True, False, False)),
                source,
                "emergency-brake",
            ),
            TargetedWitnessCase(
                program.entry,
                (state, input_value(0.0, False, False, False, True)),
                source,
                "disable-motor",
            ),
            TargetedWitnessCase(
                program.entry,
                (state, input_value(0.5, True, False, False, False)),
                source,
                "set-motor-power",
            ),
        )
    )


__all__ = [
    "PUBLIC_STRICT_ACTIVATION_VERSION",
    "PublicStrictActivation",
    "inactive_public_strict_activation_ir",
    "select_public_strict_activation",
]

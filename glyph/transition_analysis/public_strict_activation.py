from __future__ import annotations

from dataclasses import dataclass

from ..artifacts import CompilationModel
from ..compiler import ExternDecl
from .concrete import ConstructorValue, VariantValue
from .effect_contract_audit import audit_effect_contract_coverage
from .program_identity import ProgramIdentity, build_program_identity
from .public_effect_contracts import (
    BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID,
    PUBLIC_STRICT_EFFECT_SURFACE_VERSION,
    PUBLIC_STRICT_PROGRAMS,
    PublicStrictProgram,
)
from .witness_generation import TargetedWitnessCase, TargetedWitnessRegistry


PUBLIC_STRICT_ACTIVATION_VERSION = 2

# These digests identify the exact preprocessed compiler inputs reviewed for the
# public strict v1 surface. A same-name file with any semantic compiler-input edit is
# not permitted to reuse the reviewed Effect contracts or targeted witnesses.
_REVIEWED_ARTIFACT_SHA256 = {
    BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID: (
        "c9b1b541841a7ac50356a30de90331763f0b06379a0ebd3189cd5354c9943a58"
    ),
    "examples/acceptance/motor_safety.glyph": (
        "51ecd7e333aa5abb14bc5e27fc7fec825587f4b66e1d703009aaecabf03a4c72"
    ),
    "examples/acceptance/job_scheduler.glyph": (
        "11e43c4d3cafbed8389b91b3f391aa466c021a40842ae6f5e7615082b0c64828"
    ),
    "examples/door_sketch.glyph": (
        "d9aba74fb19f34b3ff98f04be25c6d2ff2aaefe7dca69f4f07379bf670e0c027"
    ),
    "examples/acceptance/rtai_strict_projection.glyph": (
        "466a2efca1d0f3d6e30060837cbf828cd807042357c0be296c0aac901786692f"
    ),
}


@dataclass(frozen=True)
class StrictActivationBlocker:
    code: str
    detail: str

    def to_ir(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class PublicStrictActivation:
    program: PublicStrictProgram
    program_identity: ProgramIdentity
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
            "reviewed_artifact_sha256": _REVIEWED_ARTIFACT_SHA256.get(
                self.program.source_id
            ),
            "program_identity": self.program_identity.to_ir(),
            "blockers": [],
        }


@dataclass(frozen=True)
class StrictActivationDecision:
    activation: PublicStrictActivation | None
    program: PublicStrictProgram | None
    current_identity: ProgramIdentity | None
    blockers: tuple[StrictActivationBlocker, ...]

    @property
    def active(self) -> bool:
        return self.activation is not None and not self.blockers

    def to_ir(self) -> dict[str, object]:
        if self.active and self.activation is not None:
            return self.activation.to_ir()
        return {
            "version": PUBLIC_STRICT_ACTIVATION_VERSION,
            "active": False,
            "surface_version": PUBLIC_STRICT_EFFECT_SURFACE_VERSION,
            "source_id": self.program.source_id if self.program is not None else None,
            "system": self.program.system if self.program is not None else None,
            "entry": self.program.entry if self.program is not None else None,
            "operations": (
                list(self.program.operations) if self.program is not None else []
            ),
            "targeted_witness_case_count": 0,
            "reviewed_artifact_sha256": (
                _REVIEWED_ARTIFACT_SHA256.get(self.program.source_id)
                if self.program is not None
                else None
            ),
            "program_identity": (
                self.current_identity.to_ir()
                if self.current_identity is not None
                else None
            ),
            "blockers": [item.to_ir() for item in self.blockers],
            "reason": self.blockers[0].code if self.blockers else "inactive",
        }


def inactive_public_strict_activation_ir(reason: str) -> dict[str, object]:
    return StrictActivationDecision(
        activation=None,
        program=None,
        current_identity=None,
        blockers=(StrictActivationBlocker(reason, reason),),
    ).to_ir()


def evaluate_public_strict_activation(
    model: CompilationModel,
    source_name: str,
) -> StrictActivationDecision:
    """Evaluate strict activation without collapsing rejection into ``None``.

    Paths select a catalog candidate only. Exact compiler-input identity, compiled
    System shape, reachable outbound Effect coverage and declaration parameter order
    are all authorization conditions. Any mismatch remains observable and fails
    closed.
    """

    candidates = tuple(
        program
        for program in PUBLIC_STRICT_PROGRAMS
        if _source_matches(program, source_name)
    )
    if not candidates:
        return StrictActivationDecision(
            None,
            None,
            None,
            (
                StrictActivationBlocker(
                    "no-reviewed-catalog-candidate",
                    "source path is not part of the reviewed public strict surface",
                ),
            ),
        )

    rejected: StrictActivationDecision | None = None
    for program in candidates:
        identity = build_program_identity(
            model,
            source_id=program.source_id,
            system=program.system,
            entry=program.entry,
        )
        blockers: list[StrictActivationBlocker] = []
        reviewed_digest = _REVIEWED_ARTIFACT_SHA256.get(program.source_id)
        if reviewed_digest is None:
            blockers.append(
                StrictActivationBlocker(
                    "reviewed-artifact-digest-missing",
                    f"no reviewed source digest exists for {program.source_id}",
                )
            )
        elif identity.artifact_sha256 != reviewed_digest:
            blockers.append(
                StrictActivationBlocker(
                    "source-content-mismatch",
                    "preprocessed compiler input does not match the reviewed artifact",
                )
            )

        if not _system_matches(model, program):
            blockers.append(
                StrictActivationBlocker(
                    "system-entry-mismatch",
                    f"expected System {program.system} entry {program.entry}",
                )
            )

        report = audit_effect_contract_coverage(
            model,
            (program.entry,),
            program.registry(),
        )
        if not report.complete or len(report.entries) != 1:
            blockers.append(
                StrictActivationBlocker(
                    "contract-coverage-incomplete",
                    "reachable outbound Effect contract audit is incomplete",
                )
            )
        elif set(report.entries[0].required_operations) != set(program.operations):
            blockers.append(
                StrictActivationBlocker(
                    "effect-surface-mismatch",
                    "reachable outbound Effect set differs from the reviewed surface",
                )
            )

        if not _contract_parameters_match(model, program):
            blockers.append(
                StrictActivationBlocker(
                    "effect-parameter-mismatch",
                    "Effect declaration parameter order differs from the contract",
                )
            )

        if not blockers:
            activation = PublicStrictActivation(
                program,
                identity,
                targeted_witnesses=_targeted_witnesses(program),
            )
            return StrictActivationDecision(activation, program, identity, ())
        if rejected is None:
            rejected = StrictActivationDecision(
                None,
                program,
                identity,
                tuple(blockers),
            )

    assert rejected is not None
    return rejected


def select_public_strict_activation(
    model: CompilationModel,
    source_name: str,
) -> PublicStrictActivation | None:
    """Compatibility wrapper for callers that only need the active profile."""

    return evaluate_public_strict_activation(model, source_name).activation


def _source_matches(program: PublicStrictProgram, source_name: str) -> bool:
    normalized = source_name.replace("\\", "/").rstrip("/")
    if program.source_id == BUILTIN_DEFAULT_WORKSPACE_SOURCE_ID:
        return (
            normalized == program.source_id
            or normalized.endswith("/.glyph/workspace.glyph")
            or normalized == ".glyph/workspace.glyph"
        )
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
    "StrictActivationBlocker",
    "StrictActivationDecision",
    "evaluate_public_strict_activation",
    "inactive_public_strict_activation_ir",
    "select_public_strict_activation",
]

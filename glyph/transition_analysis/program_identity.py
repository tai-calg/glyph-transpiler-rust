from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

from ..artifacts import CompilationModel
from ..compiler import ExternDecl, FunctionDecl, TypeRef
from .machine_relation import build_machine_relation


PROGRAM_IDENTITY_VERSION = 1
RTAI_SEMANTIC_KERNEL_VERSION = "rtai-semantic-kernel-v1"


@dataclass(frozen=True)
class ProgramIdentity:
    source_id: str
    artifact_sha256: str
    semantic_sha256: str
    entry_signature_sha256: str
    effect_declaration_sha256: str
    machine_relation_sha256: str
    analysis_kernel_id: str = RTAI_SEMANTIC_KERNEL_VERSION

    @property
    def fingerprint(self) -> str:
        return _digest(
            {
                "version": PROGRAM_IDENTITY_VERSION,
                "source_id": self.source_id,
                "artifact_sha256": self.artifact_sha256,
                "semantic_sha256": self.semantic_sha256,
                "entry_signature_sha256": self.entry_signature_sha256,
                "effect_declaration_sha256": self.effect_declaration_sha256,
                "machine_relation_sha256": self.machine_relation_sha256,
                "analysis_kernel_id": self.analysis_kernel_id,
            }
        )

    def to_ir(self) -> dict[str, object]:
        return {
            "version": PROGRAM_IDENTITY_VERSION,
            "source_id": self.source_id,
            "artifact_sha256": self.artifact_sha256,
            "semantic_sha256": self.semantic_sha256,
            "entry_signature_sha256": self.entry_signature_sha256,
            "effect_declaration_sha256": self.effect_declaration_sha256,
            "machine_relation_sha256": self.machine_relation_sha256,
            "analysis_kernel_id": self.analysis_kernel_id,
            "fingerprint": self.fingerprint,
        }


def build_program_identity(
    model: CompilationModel,
    *,
    source_id: str,
    system: str,
    entry: str,
) -> ProgramIdentity:
    """Build a deterministic identity for one reviewed public execution context.

    The artifact digest is intentionally byte-sensitive. Comments, whitespace and
    line-ending changes invalidate a reviewed artifact rather than silently reusing
    witnesses. Separate semantic component digests make the rejection diagnosable
    and provide stable binding material for Evidence and witness records.
    """

    source = model.preprocess.source
    artifact_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
    entry_ir = _entry_signature_ir(model, entry)
    effects_ir = _effect_declarations_ir(model)
    relations_ir = _machine_relations_ir(model)
    semantic_ir = {
        "identity_version": PROGRAM_IDENTITY_VERSION,
        "analysis_kernel_id": RTAI_SEMANTIC_KERNEL_VERSION,
        "system": system,
        "entry": entry,
        "entry_signature": entry_ir,
        "effects": effects_ir,
        "machine_relations": relations_ir,
    }
    return ProgramIdentity(
        source_id=source_id,
        artifact_sha256=artifact_sha256,
        semantic_sha256=_digest(semantic_ir),
        entry_signature_sha256=_digest(entry_ir),
        effect_declaration_sha256=_digest(effects_ir),
        machine_relation_sha256=_digest(relations_ir),
    )


def _entry_signature_ir(model: CompilationModel, entry: str) -> dict[str, object]:
    declaration = next(
        (
            item
            for item in model.program.declarations
            if isinstance(item, FunctionDecl) and item.name == entry
        ),
        None,
    )
    if declaration is None:
        return {"name": entry, "available": False}
    return {
        "name": declaration.name,
        "available": True,
        "parameters": [
            {
                "name": parameter.name,
                "type": _type_ir(parameter.ty),
                "ownership": _optional_attribute(parameter, "ownership"),
                "capability": _optional_attribute(parameter, "capability"),
            }
            for parameter in declaration.params
        ],
        "return_type": _type_ir(declaration.return_type),
    }


def _effect_declarations_ir(model: CompilationModel) -> list[dict[str, object]]:
    effect_names = _top_level_effect_names(model.preprocess.source)
    declarations = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, ExternDecl)
    }
    return [
        {
            "name": name,
            "parameters": [
                {"name": parameter.name, "type": _type_ir(parameter.ty)}
                for parameter in declarations[name].params
            ],
            "return_type": _type_ir(declarations[name].return_type),
        }
        if name in declarations
        else {"name": name, "available": False}
        for name in effect_names
    ]


def _machine_relations_ir(model: CompilationModel) -> list[dict[str, object]]:
    relations: list[dict[str, object]] = []
    for machine in sorted(model.machines, key=lambda item: item.name):
        relation = build_machine_relation(model, machine.name)
        if relation is None:
            relations.append({"machine": machine.name, "available": False})
            continue
        relations.append(
            {
                "machine": relation.machine_id,
                "transition_function": relation.transition_function,
                "formals": list(relation.formals),
                "edges": [
                    {
                        "ordinal": edge.ordinal,
                        "effective_guard": repr(edge.effective_guard),
                        "result_expression": repr(edge.result_expression),
                        "target_state": edge.target_state,
                        "completion": edge.completion,
                    }
                    for edge in relation.edges
                ],
                "approximation": relation.approximation.to_ir(),
            }
        )
    return relations


def _top_level_effect_names(source: str) -> tuple[str, ...]:
    names: list[str] = []
    for original in source.splitlines():
        code = original.split("#", 1)[0].rstrip()
        stripped = code.strip()
        if not stripped or code[:1].isspace() or not stripped.startswith("!"):
            continue
        signature = stripped[1:].strip()
        open_pos = signature.find("(")
        if open_pos <= 0:
            continue
        name = signature[:open_pos].strip()
        if name and name not in names:
            names.append(name)
    return tuple(names)


def _type_ir(value: TypeRef) -> dict[str, object]:
    return {
        "name": value.name,
        "arguments": [_type_ir(item) for item in value.args],
    }


def _optional_attribute(value: object, name: str) -> object:
    candidate = getattr(value, name, None)
    if candidate is None:
        return None
    return getattr(candidate, "value", candidate)


def _digest(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_default(value: object) -> object:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_ir"):
        return value.to_ir()  # type: ignore[no-any-return]
    return repr(value)


__all__ = [
    "PROGRAM_IDENTITY_VERSION",
    "RTAI_SEMANTIC_KERNEL_VERSION",
    "ProgramIdentity",
    "build_program_identity",
]

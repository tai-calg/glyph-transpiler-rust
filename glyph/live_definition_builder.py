from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

from .artifacts import CompilationModel
from .compiler import AliasDecl, ExternDecl, ProductDecl, SumDecl
from .live_image import DefinitionVersion, build_live_definitions
from .semantic import render_type


def _digest(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _definition(
    kind: str,
    name: str,
    line: int | None,
    *,
    signature: object,
    implementation: object,
) -> DefinitionVersion:
    return DefinitionVersion(
        id=f"{kind}:{name}",
        kind=kind,
        name=name,
        line=line,
        signature_digest=_digest(signature),
        implementation_digest=_digest(implementation),
        content_digest=_digest(
            {"signature": signature, "implementation": implementation}
        ),
    )


def _type_definition(declaration: object) -> DefinitionVersion | None:
    if isinstance(declaration, ProductDecl):
        signature = {
            "form": "product",
            "fields": [
                {"name": field.name, "type": render_type(field.ty)}
                for field in declaration.fields
            ],
        }
        return _definition(
            "type",
            declaration.name,
            declaration.line,
            signature=signature,
            implementation={},
        )
    if isinstance(declaration, SumDecl):
        signature = {
            "form": "sum",
            "variants": [
                {
                    "name": variant.name,
                    "tuple_types": [render_type(item) for item in variant.tuple_types],
                    "fields": [
                        {"name": field.name, "type": render_type(field.ty)}
                        for field in variant.fields
                    ],
                }
                for variant in declaration.variants
            ],
        }
        return _definition(
            "type",
            declaration.name,
            declaration.line,
            signature=signature,
            implementation={},
        )
    if isinstance(declaration, AliasDecl):
        signature = {"form": "alias", "target": render_type(declaration.target)}
        return _definition(
            "type",
            declaration.name,
            declaration.line,
            signature=signature,
            implementation={},
        )
    return None


def _extern_definition(declaration: ExternDecl) -> DefinitionVersion:
    signature = {
        "params": [
            {"name": parameter.name, "type": render_type(parameter.ty)}
            for parameter in declaration.params
        ],
        "return": render_type(declaration.return_type),
    }
    return _definition(
        "function",
        declaration.name,
        declaration.line,
        signature=signature,
        implementation={"boundary": "host"},
    )


def build_compilation_definitions(
    model: CompilationModel,
    design: dict[str, object],
) -> tuple[DefinitionVersion, ...]:
    """Build the complete Live Image manifest from compiler-internal models.

    The public typed-design JSON intentionally omits some legacy declaration shape.
    Live Studio therefore uses the already parsed CompilationModel instead of parsing
    source text again or weakening compatibility by changing the public IR.
    """

    definitions = {item.id: item for item in build_live_definitions(design)}

    for declaration in model.program.declarations:
        type_definition = _type_definition(declaration)
        if type_definition is not None:
            definitions[type_definition.id] = type_definition
        elif isinstance(declaration, ExternDecl):
            external = _extern_definition(declaration)
            definitions[external.id] = external

    for opaque in model.opaques:
        signature = {
            "params": [
                {"name": parameter.name, "type": render_type(parameter.ty)}
                for parameter in opaque.params
            ],
            "return": render_type(opaque.return_type),
        }
        definitions[f"function:{opaque.name}"] = _definition(
            "function",
            opaque.name,
            opaque.line,
            signature=signature,
            implementation={"manual": True, "note": opaque.note},
        )

    for macro in model.ast_macros:
        payload = asdict(macro)
        definitions[f"reader:{macro.name}"] = _definition(
            "reader",
            macro.name,
            macro.line,
            signature={"phase": "expand", "name": macro.name},
            implementation=payload,
        )

    for specification in model.specs:
        payload = asdict(specification)
        definitions[f"temporal:{specification.name}"] = _definition(
            "temporal",
            specification.name,
            specification.line,
            signature={"name": specification.name},
            implementation=payload,
        )

    return tuple(sorted(definitions.values(), key=lambda item: item.id))

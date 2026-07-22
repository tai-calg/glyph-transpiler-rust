from __future__ import annotations

import re

from .contracts import ContractDecl, ContractKind, ContractModel


_SHORTCUTS = {
    "F": "f32",
    "D": "f64",
    "U": "u16",
    "I": "i32",
    "B": "bool",
}
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def normalize_contract_types(model: ContractModel) -> ContractModel:
    """Apply the existing Glyph type shortcuts inside Protocol Contract bodies.

    Raw Contract IR keeps the source spelling. Canonical runtime Contract IR uses the same
    expanded type names as the ordinary Glyph parser, so `I` and `i32` cannot diverge.
    """

    declarations = []
    for declaration in model.declarations:
        body = declaration.body
        if declaration.kind is ContractKind.PROTOCOL:
            body = _WORD.sub(
                lambda match: _SHORTCUTS.get(match.group(0), match.group(0)),
                body,
            )
        declarations.append(
            ContractDecl(
                declaration.name,
                declaration.kind,
                body,
                declaration.refs,
                declaration.line,
                declaration.end_line,
            )
        )
    return ContractModel(tuple(declarations), model.applications)

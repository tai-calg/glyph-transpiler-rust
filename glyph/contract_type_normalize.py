from __future__ import annotations

from .contracts import ContractDecl, ContractKind, ContractModel
from .type_shortcuts import expand_type_words


def normalize_contract_types(model: ContractModel) -> ContractModel:
    """Normalize Protocol types while keeping the source-spelled Contract IR intact."""

    declarations = tuple(
        ContractDecl(
            declaration.name,
            declaration.kind,
            (
                expand_type_words(declaration.body)
                if declaration.kind is ContractKind.PROTOCOL
                else declaration.body
            ),
            declaration.refs,
            declaration.line,
            declaration.end_line,
        )
        for declaration in model.declarations
    )
    return ContractModel(declarations, model.applications)

from __future__ import annotations

from .compiler import Param, ProductDecl, Program
from .contracts import ContractKind, ContractModel
from .contract_semantics import ContractSemanticModel
from .temporal import SpecDecl, parse_formula


def _normalize_formula(body: str) -> str:
    return body.replace("@A", "□").replace("@E", "◇")


def build_contract_law_specs(
    contracts: ContractModel,
    runtime: ContractSemanticModel,
    program: Program,
) -> tuple[SpecDecl, ...]:
    """Bridge product-applied Law Contracts into the existing temporal monitor engine.

    Function lifecycle Laws remain in runtime-contract-ir because they need Host lifecycle
    events. Product-applied Laws have a concrete trace schema and can reuse the existing
    reference and streaming monitor code generation immediately.
    """

    law_bodies = {
        declaration.name: declaration.body
        for declaration in contracts.declarations
        if declaration.kind is ContractKind.LAW
    }
    products = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, ProductDecl)
    }
    output: list[SpecDecl] = []
    names: set[str] = set()

    for application in runtime.applications:
        if application.target_kind != "product":
            continue
        product = products.get(application.target)
        if product is None:
            continue
        params = tuple(Param(field.name, field.ty) for field in product.fields)
        for law in application.row.laws:
            body = law_bodies[law]
            name = f"contract_{law}_{product.name}"
            suffix = 2
            candidate = name
            while candidate in names:
                candidate = f"{name}_{suffix}"
                suffix += 1
            names.add(candidate)
            output.append(
                SpecDecl(
                    candidate,
                    params,
                    parse_formula(_normalize_formula(body)),
                    application.line,
                )
            )
    return tuple(output)

from __future__ import annotations

from itertools import product

from ..artifacts import CompilationModel
from ..compiler import ProductDecl, SumDecl, TypeRef
from .concrete import ConstructorValue, VariantValue


class FiniteDomainError(ValueError):
    pass


def finite_values(
    model: CompilationModel,
    type_ref: TypeRef,
    *,
    _visiting: frozenset[str] = frozenset(),
) -> tuple[object, ...]:
    """Enumerate one finite Glyph type without approximating recursive domains.

    The function is shared by concrete/abstract regression oracles and the typed
    finite solver.  Unsupported or recursive domains fail explicitly instead of
    silently becoming empty, because an empty domain would make every predicate
    appear vacuously unsatisfiable.
    """

    if type_ref.name in {"B", "bool"} and not type_ref.args:
        return (False, True)
    if type_ref.name in _visiting:
        raise FiniteDomainError(f"recursive finite domain is unsupported: {type_ref.name}")

    products = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, ProductDecl)
    }
    sums = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, SumDecl)
    }

    product_decl = products.get(type_ref.name)
    if product_decl is not None:
        visiting = _visiting | {type_ref.name}
        field_domains = [
            finite_values(model, field.ty, _visiting=visiting)
            for field in product_decl.fields
        ]
        return tuple(
            ConstructorValue(
                product_decl.name,
                tuple(
                    (field.name, value)
                    for field, value in zip(
                        product_decl.fields,
                        values,
                        strict=True,
                    )
                ),
            )
            for values in product(*field_domains)
        )

    sum_decl = sums.get(type_ref.name)
    if sum_decl is not None:
        visiting = _visiting | {type_ref.name}
        values: list[object] = []
        for variant in sum_decl.variants:
            argument_types = (
                tuple(field.ty for field in variant.fields)
                if variant.fields
                else variant.tuple_types
            )
            argument_domains = [
                finite_values(model, argument_type, _visiting=visiting)
                for argument_type in argument_types
            ]
            if not argument_domains:
                values.append(VariantValue(variant.name))
                continue
            values.extend(
                VariantValue(variant.name, tuple(arguments))
                for arguments in product(*argument_domains)
            )
        return tuple(values)

    raise FiniteDomainError(
        f"type {type_ref.name} is not a finite enumerable Bool/Product/Sum domain"
    )


def finite_assignments(
    model: CompilationModel,
    variables: tuple[tuple[str, TypeRef], ...],
    *,
    max_cases: int,
) -> tuple[dict[str, object], ...]:
    domains = [finite_values(model, type_ref) for _, type_ref in variables]
    total = 1
    for domain in domains:
        total *= len(domain)
    if total > max_cases:
        raise FiniteDomainError(
            f"finite domain requires {total} assignments, limit is {max_cases}"
        )
    return tuple(
        {
            name: value
            for (name, _), value in zip(variables, values, strict=True)
        }
        for values in product(*domains)
    )

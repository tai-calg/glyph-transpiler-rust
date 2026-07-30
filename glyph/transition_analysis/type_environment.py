from __future__ import annotations

from ..artifacts import CompilationModel
from ..compiler import Expr, FunctionDecl, NameExpr, TypeRef


def unique_parameter_types(
    model: CompilationModel,
    expression: Expr,
) -> dict[str, TypeRef]:
    """Return only free-name types that are unique across parsed signatures."""

    names = expression_names(expression)
    candidates: dict[str, set[TypeRef]] = {name: set() for name in names}
    for declaration in model.program.declarations:
        if not isinstance(declaration, FunctionDecl):
            continue
        for parameter in declaration.params:
            if parameter.name in candidates:
                candidates[parameter.name].add(parameter.ty)
    return {
        name: next(iter(types))
        for name, types in candidates.items()
        if len(types) == 1
    }


def expression_names(expression: Expr) -> frozenset[str]:
    names: set[str] = set()

    def visit(value: object, *, is_callee: bool = False) -> None:
        if isinstance(value, NameExpr):
            if not is_callee:
                names.add(value.name)
            return
        if not isinstance(value, Expr):
            return
        fields = vars(value).items() if hasattr(value, "__dict__") else ()
        for field_name, child in fields:
            if isinstance(child, Expr):
                visit(child, is_callee=field_name == "callee")
            elif isinstance(child, tuple):
                for item in child:
                    visit(item)

    visit(expression)
    return frozenset(names)

from __future__ import annotations

import re

from .capabilities import CapabilityFunction, CapabilityKind, CapabilityModel
from .compiler import (
    BinaryExpr,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    GlyphError,
    NameExpr,
    ProductDecl,
    Program,
    TryExpr,
    UnaryExpr,
)
from .contracts import ContractModel
from .contract_semantics import AppliedContract, ContractRow, ContractSemanticModel


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_FIELD_RE = re.compile(rf"(?P<name>{_IDENT})\s*:")
_TOP_RE = re.compile(rf"^[*+=>!~]\s*(?P<name>{_IDENT})")
_RECOVERY = {"return_error", "rollback", "compensate", "fallback"}


def _line_target(source: str, line: int, default: AppliedContract) -> tuple[str, str]:
    lines = source.splitlines()
    if not (1 <= line <= len(lines)):
        return default.target, default.target_kind
    current = lines[line - 1].split("#", 1)[0]
    marker = current.find("@{")
    prefix = current[:marker] if marker >= 0 else current
    if current[:1].isspace():
        matches = list(_FIELD_RE.finditer(prefix))
        if matches:
            field = matches[-1].group("name")
            owner = None
            for index in range(line - 2, -1, -1):
                candidate = lines[index].split("#", 1)[0].rstrip()
                if not candidate.strip() or candidate[:1].isspace():
                    continue
                top = _TOP_RE.match(candidate.strip())
                if top is not None:
                    owner = top.group("name")
                break
            if owner is not None:
                return f"{owner}.{field}", "field"
    return default.target, default.target_kind


def _merge(left: ContractRow, right: ContractRow, line: int) -> ContractRow:
    def one(kind: str, a: str | None, b: str | None) -> str | None:
        if a is not None and b is not None and a != b:
            raise GlyphError(f"{line}行目: 同じ対象へ異なる{kind} Contractを適用できない")
        return a or b

    return ContractRow(
        one("World", left.world, right.world),
        one("Protocol", left.protocol, right.protocol),
        one("Handler", left.handler, right.handler),
        tuple(dict.fromkeys((*left.laws, *right.laws))),
    )


def _signature(function: CapabilityFunction) -> tuple[tuple[str, ...], str]:
    return tuple(parameter.type.name for parameter in function.params), function.result.name


def _validate_handlers(model: ContractSemanticModel, capabilities: CapabilityModel, program: Program) -> None:
    handlers = {item.name: item for item in model.handlers}
    functions = {item.name: item for item in capabilities.functions}
    effects = {item.name for item in program.declarations if isinstance(item, ExternDecl)}

    for application in model.applications:
        if application.row.handler is None:
            continue
        handler = handlers[application.row.handler]
        recoveries = [step for step in handler.steps if step.operation in _RECOVERY]
        if len(recoveries) > 1:
            names = ", ".join(step.operation for step in recoveries)
            raise GlyphError(
                f"{application.line}行目: Handler '{handler.name}' の最終復旧は"
                f"1個だけにする: {names}"
            )
        for step in handler.steps:
            if step.operation == "retry":
                if int(step.arguments[0]) <= 0:
                    raise GlyphError(f"{step.line}行目: retry回数は0より大きくする")
                if not step.arguments[1].replace(" ", "").startswith("'std."):
                    raise GlyphError(f"{step.line}行目: retry backoffはContract参照で指定する")
            elif step.operation == "compensate":
                target = step.arguments[0].lstrip("'").strip()
                if target not in effects:
                    raise GlyphError(
                        f"{step.line}行目: compensation '{target}' は!作用境界でなければならない"
                    )
            elif step.operation == "fallback":
                target = step.arguments[0].lstrip("'").strip()
                source_function = functions.get(application.target)
                fallback = functions.get(target)
                if source_function is None or fallback is None:
                    raise GlyphError(f"{step.line}行目: fallback '{target}' の関数署名を解決できない")
                if _signature(source_function) != _signature(fallback):
                    raise GlyphError(
                        f"{step.line}行目: fallback '{target}' は"
                        f"'{application.target}'と同じ入出力型を持たなければならない"
                    )


def _walk(expr: Expr):
    yield expr
    if isinstance(expr, (UnaryExpr, TryExpr)):
        yield from _walk(expr.expr)
    elif isinstance(expr, BinaryExpr):
        yield from _walk(expr.left)
        yield from _walk(expr.right)
    elif isinstance(expr, FieldExpr):
        yield from _walk(expr.base)
    elif isinstance(expr, CallExpr):
        yield from _walk(expr.callee)
        for argument in expr.args:
            yield from _walk(argument)


def _roots(function: FunctionDecl) -> tuple[Expr, ...]:
    if function.expression is not None:
        return (function.expression,)
    output = []
    for guard in function.guards:
        if guard.condition is not None:
            output.append(guard.condition)
        output.append(guard.value)
    return tuple(output)


def _region_relation(target: tuple[str, ...], source: tuple[str, ...]) -> str:
    if not target or not source or target[0] != source[0]:
        return "incompatible"
    if len(target) <= len(source) and source[: len(target)] == target:
        return "broader" if len(target) < len(source) else "equal"
    if len(source) < len(target) and target[: len(source)] == source:
        return "narrower"
    return "incompatible"


def _validate_region_escapes(model: ContractSemanticModel, capabilities: CapabilityModel, program: Program) -> None:
    worlds = {item.name: item for item in model.worlds}
    applications = {item.target: item for item in model.applications}
    capability_functions = {item.name: item for item in capabilities.functions}
    products = {item.name: item for item in program.declarations if isinstance(item, ProductDecl)}

    for declaration in program.declarations:
        if not isinstance(declaration, FunctionDecl):
            continue
        function_application = applications.get(declaration.name)
        if function_application is None or function_application.row.world is None:
            continue
        function_world = worlds[function_application.row.world]
        capability_function = capability_functions.get(declaration.name)
        if capability_function is None:
            continue
        params = {item.name: item.type for item in capability_function.params}

        for root in _roots(declaration):
            for expression in _walk(root):
                if not (isinstance(expression, CallExpr) and isinstance(expression.callee, NameExpr)):
                    continue
                product = products.get(expression.callee.name)
                if product is None:
                    continue
                for field, argument in zip(product.fields, expression.args):
                    if not isinstance(argument, NameExpr):
                        continue
                    source_type = params.get(argument.name)
                    field_application = applications.get(f"{product.name}.{field.name}")
                    if source_type is None or field_application is None or field_application.row.world is None:
                        continue
                    if source_type.capability is CapabilityKind.LINK:
                        continue
                    target_world = worlds[field_application.row.world]
                    relation = _region_relation(target_world.region, function_world.region)
                    if relation in {"broader", "incompatible"}:
                        raise GlyphError(
                            f"{declaration.line}行目: '{argument.name}' は"
                            f"{'/'.join(function_world.region)}から"
                            f"{'/'.join(target_world.region)}へescapeできない。"
                            "長期観測にはlinkを使う"
                        )


def validate_and_refine_runtime_contracts(
    source: str,
    model: ContractSemanticModel,
    contracts: ContractModel,
    capabilities: CapabilityModel,
    program: Program,
) -> ContractSemanticModel:
    refined: list[AppliedContract] = []
    by_target: dict[str, AppliedContract] = {}
    for application in model.applications:
        target, kind = _line_target(source, application.line, application)
        row = application.row
        if kind == "field" and (row.protocol is not None or row.handler is not None):
            raise GlyphError(f"{application.line}行目: fieldへ適用できるのはWorldとLaw Contractだけ")
        existing = by_target.get(target)
        if existing is not None:
            row = _merge(existing.row, row, application.line)
            refined_application = AppliedContract(target, kind, row, existing.line)
            refined.remove(existing)
        else:
            refined_application = AppliedContract(target, kind, row, application.line)
        by_target[target] = refined_application
        refined.append(refined_application)

    result = ContractSemanticModel(model.worlds, model.protocols, model.handlers, model.laws, model.rows, tuple(refined))
    _validate_handlers(result, capabilities, program)
    _validate_region_escapes(result, capabilities, program)
    return result

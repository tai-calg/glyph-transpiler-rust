from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Mapping, Sequence

from .capabilities import (
    AggregateType,
    CapabilityKind,
    CapabilityModel,
    CapabilityType,
)
from .compiler import (
    BinaryExpr,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    NameExpr,
    ProductDecl,
    Program,
    SumDecl,
    TryExpr,
    UnaryExpr,
)
from .execution_ir import render_expr
from .function_blocks import FunctionBlockLowering
from .pipeline import _render_type


_SCHEMA = "glyph.monoidal-ir"
_VERSION = 1
_BUILTINS = {"Ok", "Err", "Some", "None", "min", "max", "finite"}


@dataclass(frozen=True)
class MonoidalSourceRef:
    line: int
    column: int = 1


@dataclass(frozen=True)
class TensorFactor:
    name: str
    type: str
    expression: str | None = None
    capability: str | None = None
    state: str | None = None


@dataclass(frozen=True)
class TensorNode:
    id: str
    function: str | None
    role: str
    label: str
    product_type: str | None
    factors: tuple[TensorFactor, ...]
    resource: bool
    source: MonoidalSourceRef


@dataclass(frozen=True)
class ParallelLane:
    index: int
    label: str
    expression: str
    calls: tuple[str, ...]
    source: MonoidalSourceRef


@dataclass(frozen=True)
class ParallelNode:
    id: str
    function: str
    tensor_id: str
    semantics: str
    lanes: tuple[ParallelLane, ...]
    source: MonoidalSourceRef


@dataclass(frozen=True)
class MonoidalIR:
    source_name: str
    tensors: tuple[TensorNode, ...]
    parallels: tuple[ParallelNode, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        return {"schema": _SCHEMA, "version": _VERSION, **payload}


@dataclass(frozen=True)
class _ExpressionSite:
    function: str
    expression: Expr
    line: int


def _safe(text: str) -> str:
    value = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in text)
    return value or "node"


def _walk(expr: Expr) -> Iterable[Expr]:
    yield expr
    if isinstance(expr, UnaryExpr):
        yield from _walk(expr.expr)
    elif isinstance(expr, TryExpr):
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


def _calls(expr: Expr) -> tuple[str, ...]:
    result: list[str] = []
    for item in _walk(expr):
        if not isinstance(item, CallExpr) or not isinstance(item.callee, NameExpr):
            continue
        if item.callee.name not in result:
            result.append(item.callee.name)
    return tuple(result)


def _contains_try(expr: Expr) -> bool:
    return any(isinstance(item, TryExpr) for item in _walk(expr))


def _function_expressions(declaration: FunctionDecl) -> tuple[Expr, ...]:
    if declaration.expression is not None:
        return (declaration.expression,)
    values: list[Expr] = []
    for clause in declaration.guards:
        if clause.condition is not None:
            values.append(clause.condition)
        values.append(clause.value)
    return tuple(values)


def _purity_table(program: Program) -> dict[str, bool]:
    functions = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, FunctionDecl)
    }
    externs = {
        declaration.name
        for declaration in program.declarations
        if isinstance(declaration, ExternDecl)
    }
    products = {
        declaration.name
        for declaration in program.declarations
        if isinstance(declaration, ProductDecl)
    }
    variants = {
        variant.name
        for declaration in program.declarations
        if isinstance(declaration, SumDecl)
        for variant in declaration.variants
    }
    constructors = products | variants | _BUILTINS
    memo: dict[str, bool] = {}

    def pure(name: str, visiting: frozenset[str]) -> bool:
        if name in memo:
            return memo[name]
        if name in externs:
            memo[name] = False
            return False
        if name in constructors:
            return True
        declaration = functions.get(name)
        if declaration is None or name in visiting:
            return False
        next_visiting = visiting | {name}
        for expression in _function_expressions(declaration):
            for item in _walk(expression):
                if not isinstance(item, CallExpr):
                    continue
                if not isinstance(item.callee, NameExpr):
                    memo[name] = False
                    return False
                if not pure(item.callee.name, next_visiting):
                    memo[name] = False
                    return False
        memo[name] = True
        return True

    for name in functions:
        pure(name, frozenset())
    return memo


def _expression_is_parallel_safe(
    expr: Expr,
    purity: Mapping[str, bool],
    constructors: set[str],
) -> bool:
    # `?` introduces ordered early-return semantics. Even when every called function is
    # otherwise pure, changing lane evaluation order could select a different first error.
    if _contains_try(expr):
        return False
    for item in _walk(expr):
        if not isinstance(item, CallExpr):
            continue
        if not isinstance(item.callee, NameExpr):
            return False
        name = item.callee.name
        if name in constructors or name in _BUILTINS:
            continue
        if not purity.get(name, False):
            return False
    return True


def _helper_sites(
    blocks: Sequence[FunctionBlockLowering],
) -> tuple[dict[str, tuple[str, int]], set[str]]:
    helpers: dict[str, tuple[str, int]] = {}
    block_names: set[str] = set()
    for block in blocks:
        block_names.add(block.name)
        for binding in block.bindings:
            helpers[binding.value_helper] = (block.name, binding.line)
        helpers[block.final_helper] = (block.name, block.final_line)
    return helpers, block_names


def _expression_sites(
    program: Program,
    blocks: Sequence[FunctionBlockLowering],
) -> tuple[_ExpressionSite, ...]:
    helper_sites, block_names = _helper_sites(blocks)
    sites: list[_ExpressionSite] = []
    for declaration in program.declarations:
        if not isinstance(declaration, FunctionDecl):
            continue
        if declaration.name in helper_sites:
            function, line = helper_sites[declaration.name]
        elif declaration.name.startswith("__glyph_") or declaration.name in block_names:
            continue
        else:
            function, line = declaration.name, declaration.line
        if declaration.expression is not None:
            sites.append(_ExpressionSite(function, declaration.expression, line))
        else:
            for clause in declaration.guards:
                sites.append(_ExpressionSite(function, clause.value, clause.line))
    return tuple(sites)


def _product_type_tensors(program: Program) -> list[TensorNode]:
    result: list[TensorNode] = []
    for declaration in program.declarations:
        if not isinstance(declaration, ProductDecl) or len(declaration.fields) < 2:
            continue
        result.append(
            TensorNode(
                id=f"tensor_type_{_safe(declaration.name)}",
                function=None,
                role="product_type",
                label=f"{declaration.name} = "
                + " ⊗ ".join(field.name for field in declaration.fields),
                product_type=declaration.name,
                factors=tuple(
                    TensorFactor(field.name, _render_type(field.ty))
                    for field in declaration.fields
                ),
                resource=False,
                source=MonoidalSourceRef(declaration.line),
            )
        )
    return result


def _product_value_nodes(
    program: Program,
    blocks: Sequence[FunctionBlockLowering],
) -> tuple[list[TensorNode], list[ParallelNode]]:
    products = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, ProductDecl)
    }
    variants = {
        variant.name
        for declaration in program.declarations
        if isinstance(declaration, SumDecl)
        for variant in declaration.variants
    }
    constructors = set(products) | variants
    purity = _purity_table(program)
    tensors: list[TensorNode] = []
    parallels: list[ParallelNode] = []
    ordinal = 0

    for site in _expression_sites(program, blocks):
        for item in _walk(site.expression):
            if not (
                isinstance(item, CallExpr)
                and isinstance(item.callee, NameExpr)
                and item.callee.name in products
            ):
                continue
            declaration = products[item.callee.name]
            if len(declaration.fields) < 2 or len(item.args) != len(declaration.fields):
                continue
            ordinal += 1
            tensor_id = (
                f"tensor_value_{_safe(site.function)}_{site.line}_"
                f"{_safe(declaration.name)}_{ordinal}"
            )
            factors = tuple(
                TensorFactor(
                    field.name,
                    _render_type(field.ty),
                    expression=render_expr(argument),
                )
                for field, argument in zip(declaration.fields, item.args)
            )
            tensors.append(
                TensorNode(
                    id=tensor_id,
                    function=site.function,
                    role="product_value",
                    label=f"{declaration.name} value",
                    product_type=declaration.name,
                    factors=factors,
                    resource=False,
                    source=MonoidalSourceRef(site.line),
                )
            )
            if all(
                _expression_is_parallel_safe(argument, purity, constructors)
                for argument in item.args
            ):
                parallels.append(
                    ParallelNode(
                        id=f"parallel_{_safe(site.function)}_{site.line}_{ordinal}",
                        function=site.function,
                        tensor_id=tensor_id,
                        semantics="structural-independent; execution-order-unspecified",
                        lanes=tuple(
                            ParallelLane(
                                index=index,
                                label=field.name,
                                expression=render_expr(argument),
                                calls=_calls(argument),
                                source=MonoidalSourceRef(site.line),
                            )
                            for index, (field, argument) in enumerate(
                                zip(declaration.fields, item.args)
                            )
                        ),
                        source=MonoidalSourceRef(site.line),
                    )
                )
    return tensors, parallels


def _capability_text(ty: CapabilityType) -> str:
    if ty.raw:
        return ty.raw
    prefix = "" if ty.capability is CapabilityKind.PLAIN else ty.capability.value + " "
    if ty.name == "tuple":
        body = "(" + ",".join(_capability_text(item) for item in ty.args) + ")"
    elif ty.args:
        body = ty.name + "<" + ",".join(_capability_text(item) for item in ty.args) + ">"
    else:
        body = ty.name
    if ty.state:
        body += f"[{ty.state}]"
    return prefix + body


def _resource_factors(
    ty: CapabilityType,
    *,
    path: str,
    resources: set[str],
    aggregates: Mapping[str, AggregateType],
    seen: frozenset[str] = frozenset(),
) -> list[TensorFactor]:
    if ty.name in resources:
        return [
            TensorFactor(
                name=path,
                type=_capability_text(ty),
                capability=ty.capability.value,
                state=ty.state,
            )
        ]
    if ty.name == "tuple":
        result: list[TensorFactor] = []
        for index, item in enumerate(ty.args):
            result.extend(
                _resource_factors(
                    item,
                    path=f"{path}.{index}",
                    resources=resources,
                    aggregates=aggregates,
                    seen=seen,
                )
            )
        return result
    aggregate = aggregates.get(ty.name)
    if aggregate is None or ty.name in seen:
        return []
    result = []
    next_seen = seen | {ty.name}
    for index, member in enumerate(aggregate.members):
        result.extend(
            _resource_factors(
                member,
                path=f"{path}.{index}",
                resources=resources,
                aggregates=aggregates,
                seen=next_seen,
            )
        )
    return result


def _resource_output_groups(
    ty: CapabilityType,
    *,
    resources: set[str],
    aggregates: Mapping[str, AggregateType],
) -> tuple[tuple[str, list[TensorFactor]], ...]:
    if ty.name == "result" and len(ty.args) == 2:
        groups: list[tuple[str, list[TensorFactor]]] = []
        for role, argument in (
            ("resource_output_ok", ty.args[0]),
            ("resource_output_err", ty.args[1]),
        ):
            factors = _resource_factors(
                argument,
                path="return.ok" if role.endswith("ok") else "return.err",
                resources=resources,
                aggregates=aggregates,
            )
            if factors:
                groups.append((role, factors))
        return tuple(groups)
    return (
        (
            "resource_output",
            _resource_factors(
                ty,
                path="return",
                resources=resources,
                aggregates=aggregates,
            ),
        ),
    )


def _resource_tensors(model: CapabilityModel) -> list[TensorNode]:
    resources = {resource.name for resource in model.resources}
    aggregates = {aggregate.name: aggregate for aggregate in model.aggregates}
    result: list[TensorNode] = []
    for function in model.functions:
        input_factors: list[TensorFactor] = []
        for parameter in function.params:
            input_factors.extend(
                _resource_factors(
                    parameter.type,
                    path=parameter.name,
                    resources=resources,
                    aggregates=aggregates,
                )
            )
        if len(input_factors) >= 2:
            result.append(
                TensorNode(
                    id=f"tensor_resource_{_safe(function.name)}_input",
                    function=function.name,
                    role="resource_input",
                    label=f"{function.name} capability input",
                    product_type=None,
                    factors=tuple(input_factors),
                    resource=True,
                    source=MonoidalSourceRef(function.line),
                )
            )

        for role, output_factors in _resource_output_groups(
            function.result,
            resources=resources,
            aggregates=aggregates,
        ):
            if len(output_factors) < 2:
                continue
            result.append(
                TensorNode(
                    id=f"tensor_resource_{_safe(function.name)}_{role}",
                    function=function.name,
                    role=role,
                    label=f"{function.name} capability output",
                    product_type=None,
                    factors=tuple(output_factors),
                    resource=True,
                    source=MonoidalSourceRef(function.line),
                )
            )
    return result


def build_monoidal_ir(
    source_name: str,
    program: Program,
    blocks: Sequence[FunctionBlockLowering],
    capabilities: CapabilityModel,
) -> MonoidalIR:
    """Project validated Glyph into monoidal structure without changing surface syntax.

    Product declarations become type-level tensor nodes. Product constructor calls become
    value-level tensor nodes. A constructor also receives a Parallel node only when every
    lane is pure and contains no `?`, so the IR does not silently reorder effects or choose
    a different first error. Capability tensors describe simultaneous resource ownership;
    they are structural and do not promise runtime concurrency.
    """

    tensors = _product_type_tensors(program)
    value_tensors, parallels = _product_value_nodes(program, blocks)
    tensors.extend(value_tensors)
    tensors.extend(_resource_tensors(capabilities))
    return MonoidalIR(source_name, tuple(tensors), tuple(parallels))

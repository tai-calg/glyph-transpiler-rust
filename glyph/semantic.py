from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Mapping, Sequence

from .ast_macros import AstMacroDef
from .compiler import (
    AliasDecl,
    BinaryExpr,
    BoolExpr,
    CallExpr,
    ExternDecl,
    Expr,
    FieldExpr,
    FunctionDecl,
    NameExpr,
    NumberExpr,
    ProductDecl,
    Program,
    SumDecl,
    TryExpr,
    TypeRef,
    UnaryExpr,
)
from .functional import as_function_type, function_signature_type
from .machine import MachineDecl
from .symbols import SymbolId, SymbolInterner, SymbolRecord
from .temporal import SpecDecl


def render_type(ty: TypeRef) -> str:
    if not ty.args:
        return ty.name
    return f"{ty.name}<{','.join(render_type(arg) for arg in ty.args)}>"


@dataclass(frozen=True)
class TypedExpr:
    kind: str
    type_name: str
    symbol_id: SymbolId | None = None
    value: str | None = None
    children: tuple["TypedExpr", ...] = ()
    line: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "type": self.type_name,
            "symbol_id": None if self.symbol_id is None else self.symbol_id.value,
            "value": self.value,
            "line": self.line,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(frozen=True)
class RecursionInfo:
    recursive: bool
    analysis: str
    cycle: tuple[str, ...] = ()


@dataclass(frozen=True)
class TypedFunction:
    symbol_id: SymbolId
    name: str
    params: tuple[SymbolId, ...]
    return_type: str
    body: TypedExpr
    recursion: RecursionInfo
    line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol_id": self.symbol_id.value,
            "name": self.name,
            "params": [item.value for item in self.params],
            "return_type": self.return_type,
            "body": self.body.to_dict(),
            "recursion": asdict(self.recursion),
            "line": self.line,
        }


@dataclass(frozen=True)
class TypedMachine:
    symbol_id: SymbolId
    name: str
    selector: TypedExpr
    initial: TypedExpr
    next_expr: TypedExpr
    success_symbol: SymbolId | None
    failure_symbol: SymbolId | None
    line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol_id": self.symbol_id.value,
            "name": self.name,
            "selector": self.selector.to_dict(),
            "initial": self.initial.to_dict(),
            "next": self.next_expr.to_dict(),
            "success_symbol": None if self.success_symbol is None else self.success_symbol.value,
            "failure_symbol": None if self.failure_symbol is None else self.failure_symbol.value,
            "line": self.line,
        }


@dataclass(frozen=True)
class SemanticModel:
    symbols: tuple[SymbolRecord, ...]
    functions: tuple[TypedFunction, ...]
    machines: tuple[TypedMachine, ...]
    macros: tuple[SymbolId, ...]
    temporal: tuple[SymbolId, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "symbols": [
                {
                    "id": record.id.value,
                    "name": record.name,
                    "kind": record.kind,
                    "line": record.line,
                    "type": record.type_name,
                }
                for record in self.symbols
            ],
            "functions": [function.to_dict() for function in self.functions],
            "machines": [machine.to_dict() for machine in self.machines],
            "macros": [item.value for item in self.macros],
            "temporal": [item.value for item in self.temporal],
        }

    def function(self, name: str) -> TypedFunction | None:
        return next((item for item in self.functions if item.name == name), None)

    def symbol(self, name: str) -> SymbolRecord | None:
        return next((item for item in self.symbols if item.name == name), None)


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
        for arg in expr.args:
            yield from _walk(arg)


def _function_roots(decl: FunctionDecl) -> tuple[Expr, ...]:
    if decl.expression is not None:
        return (decl.expression,)
    roots: list[Expr] = []
    for clause in decl.guards:
        if clause.condition is not None:
            roots.append(clause.condition)
        roots.append(clause.value)
    return tuple(roots)


def _call_graph(functions: Mapping[str, FunctionDecl]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {name: set() for name in functions}
    for name, decl in functions.items():
        for root in _function_roots(decl):
            for expr in _walk(root):
                if (
                    isinstance(expr, CallExpr)
                    and isinstance(expr.callee, NameExpr)
                    and expr.callee.name in functions
                ):
                    graph[name].add(expr.callee.name)
    return graph


def _find_cycle(start: str, graph: Mapping[str, set[str]]) -> tuple[str, ...]:
    def visit(node: str, path: tuple[str, ...]) -> tuple[str, ...]:
        if node in path:
            index = path.index(node)
            return (*path[index:], node)
        for target in sorted(graph.get(node, ())):
            cycle = visit(target, (*path, node))
            if cycle:
                return cycle
        return ()

    return visit(start, ())


def _is_decreasing_argument(expr: Expr, params: set[str]) -> bool:
    return (
        isinstance(expr, BinaryExpr)
        and expr.op == "-"
        and isinstance(expr.left, NameExpr)
        and expr.left.name in params
        and isinstance(expr.right, NumberExpr)
    )


def _recursion_info(decl: FunctionDecl, graph: Mapping[str, set[str]]) -> RecursionInfo:
    cycle = _find_cycle(decl.name, graph)
    if not cycle:
        return RecursionInfo(False, "none")
    if len(set(cycle[:-1])) > 1:
        return RecursionInfo(True, "unchecked", cycle)

    params = {param.name for param in decl.params}
    recursive_calls = [
        expr
        for root in _function_roots(decl)
        for expr in _walk(root)
        if isinstance(expr, CallExpr)
        and isinstance(expr.callee, NameExpr)
        and expr.callee.name == decl.name
    ]
    structural = bool(recursive_calls) and all(
        any(_is_decreasing_argument(arg, params) for arg in call.args)
        for call in recursive_calls
    )
    return RecursionInfo(True, "structural" if structural else "unchecked", cycle)


class _Typer:
    def __init__(self, program: Program, interner: SymbolInterner):
        self.interner = interner
        self.products = {decl.name: decl for decl in program.declarations if isinstance(decl, ProductDecl)}
        self.sums = {decl.name: decl for decl in program.declarations if isinstance(decl, SumDecl)}
        self.variants = {
            variant.name: (decl, variant)
            for decl in self.sums.values()
            for variant in decl.variants
        }
        self.functions = {decl.name: decl for decl in program.declarations if isinstance(decl, FunctionDecl)}
        self.externs = {decl.name: decl for decl in program.declarations if isinstance(decl, ExternDecl)}

    def expr(
        self,
        expr: Expr,
        locals_: Mapping[str, tuple[SymbolId, TypeRef]],
        line: int,
        expected: TypeRef | None = None,
    ) -> TypedExpr:
        if isinstance(expr, NameExpr):
            local = locals_.get(expr.name)
            if local is not None:
                symbol_id, ty = local
                return TypedExpr("name", render_type(ty), symbol_id, expr.name, line=line)
            function = self.functions.get(expr.name)
            if function is not None:
                symbol_id = self.interner.lookup(expr.name, ("function",))
                ty = function_signature_type(function.params, function.return_type)
                return TypedExpr("function-value", render_type(ty), symbol_id, expr.name, line=line)
            resolved_variant = self.variants.get(expr.name)
            if resolved_variant is not None:
                enum_decl, _ = resolved_variant
                symbol_id = self.interner.lookup(expr.name, ("variant",))
                return TypedExpr("variant", enum_decl.name, symbol_id, expr.name, line=line)
            return TypedExpr("name", "unknown", value=expr.name, line=line)

        if isinstance(expr, NumberExpr):
            return TypedExpr("number", "f32" if "." in expr.value else "integer", value=expr.value, line=line)
        if isinstance(expr, BoolExpr):
            return TypedExpr("bool", "bool", value=str(expr.value).lower(), line=line)
        if isinstance(expr, UnaryExpr):
            child = self.expr(expr.expr, locals_, line)
            return TypedExpr("unary", "bool" if expr.op == "!" else child.type_name, value=expr.op, children=(child,), line=line)
        if isinstance(expr, BinaryExpr):
            left = self.expr(expr.left, locals_, line)
            right = self.expr(expr.right, locals_, line)
            ty = "bool" if expr.op in {"|", "&", "==", "!=", "<", ">", "<=", ">="} else left.type_name
            return TypedExpr("binary", ty, value=expr.op, children=(left, right), line=line)
        if isinstance(expr, FieldExpr):
            base = self.expr(expr.base, locals_, line)
            product = self.products.get(base.type_name)
            field_ty = next((field.ty for field in product.fields if field.name == expr.field), None) if product is not None else None
            return TypedExpr(
                "field",
                "unknown" if field_ty is None else render_type(field_ty),
                value=expr.field,
                children=(base,),
                line=line,
            )
        if isinstance(expr, TryExpr):
            child = self.expr(expr.expr, locals_, line)
            inner = child.type_name[2:-1].split(",", 1)[0] if child.type_name.startswith("R<") else "unknown"
            return TypedExpr("try", inner, children=(child,), line=line)
        if isinstance(expr, CallExpr):
            callee = self.expr(expr.callee, locals_, line)
            args = tuple(self.expr(arg, locals_, line) for arg in expr.args)
            result_ty = "unknown"
            symbol_id = callee.symbol_id
            value = callee.value
            if isinstance(expr.callee, NameExpr):
                name = expr.callee.name
                if name in self.functions:
                    result_ty = render_type(self.functions[name].return_type)
                elif name in self.externs:
                    result_ty = render_type(self.externs[name].return_type)
                    symbol_id = self.interner.lookup(name, ("effect",))
                elif name in self.products:
                    result_ty = name
                    symbol_id = self.interner.lookup(name, ("type",))
                elif name in self.variants:
                    result_ty = self.variants[name][0].name
                    symbol_id = self.interner.lookup(name, ("variant",))
                elif name in locals_:
                    function_ty = as_function_type(locals_[name][1])
                    if function_ty is not None:
                        result_ty = render_type(function_ty.result)
                elif name in {"min", "max"} and args:
                    result_ty = args[0].type_name
                elif name == "finite":
                    result_ty = "bool"
                elif name in {"Ok", "Err"} and expected is not None:
                    result_ty = render_type(expected)
            return TypedExpr("call", result_ty, symbol_id=symbol_id, value=value, children=(callee, *args), line=line)
        raise TypeError(f"unknown expression: {expr!r}")


def build_semantic_model(
    program: Program,
    machines: Sequence[MachineDecl] = (),
    macros: Sequence[AstMacroDef] = (),
    specs: Sequence[SpecDecl] = (),
) -> SemanticModel:
    interner = SymbolInterner()

    for decl in program.declarations:
        if isinstance(decl, (ProductDecl, SumDecl, AliasDecl)):
            interner.intern(decl.name, "type", decl.line, decl.name)
        elif isinstance(decl, FunctionDecl):
            interner.intern(
                decl.name,
                "function",
                decl.line,
                render_type(function_signature_type(decl.params, decl.return_type)),
            )
        elif isinstance(decl, ExternDecl):
            interner.intern(decl.name, "effect", decl.line, render_type(decl.return_type))
        if isinstance(decl, SumDecl):
            for variant in decl.variants:
                interner.intern(variant.name, "variant", decl.line, decl.name)

    macro_ids = tuple(interner.intern(macro.name, "macro", macro.line) for macro in macros)
    temporal_ids = tuple(interner.intern(spec.name, "temporal", spec.line) for spec in specs)
    machine_ids = {
        machine.name: interner.intern(machine.name, "machine", machine.line)
        for machine in machines
    }

    typer = _Typer(program, interner)
    functions = {decl.name: decl for decl in program.declarations if isinstance(decl, FunctionDecl)}
    graph = _call_graph(functions)
    typed_functions: list[TypedFunction] = []

    for decl in functions.values():
        function_id = interner.lookup(decl.name, ("function",))
        assert function_id is not None
        locals_: dict[str, tuple[SymbolId, TypeRef]] = {}
        param_ids: list[SymbolId] = []
        for param in decl.params:
            param_id = interner.intern(
                f"{decl.name}.{param.name}",
                "parameter",
                decl.line,
                render_type(param.ty),
            )
            locals_[param.name] = (param_id, param.ty)
            param_ids.append(param_id)

        if decl.expression is not None:
            body = typer.expr(decl.expression, locals_, decl.line, decl.return_type)
        else:
            branch_nodes: list[TypedExpr] = []
            for clause in decl.guards:
                value = typer.expr(clause.value, locals_, clause.line, decl.return_type)
                if clause.condition is None:
                    branch_nodes.append(TypedExpr("fallback", value.type_name, children=(value,), line=clause.line))
                else:
                    condition = typer.expr(clause.condition, locals_, clause.line)
                    branch_nodes.append(TypedExpr("branch", value.type_name, children=(condition, value), line=clause.line))
            body = TypedExpr("guard", render_type(decl.return_type), children=tuple(branch_nodes), line=decl.line)

        typed_functions.append(
            TypedFunction(
                function_id,
                decl.name,
                tuple(param_ids),
                render_type(decl.return_type),
                body,
                _recursion_info(decl, graph),
                decl.line,
            )
        )

    typed_machines: list[TypedMachine] = []
    for machine in machines:
        locals_ = {
            param.name: (
                interner.intern(
                    f"{machine.name}.{param.name}",
                    "machine-parameter",
                    machine.line,
                    render_type(param.ty),
                ),
                param.ty,
            )
            for param in machine.params
        }
        typed_machines.append(
            TypedMachine(
                machine_ids[machine.name],
                machine.name,
                typer.expr(machine.selector, locals_, machine.selector_line),
                typer.expr(machine.initial, locals_, machine.initial_line),
                typer.expr(machine.next_expr, locals_, machine.next_line),
                interner.lookup(machine.success, ("variant",)),
                interner.lookup(machine.failure, ("variant",)),
                machine.line,
            )
        )

    return SemanticModel(interner.records, tuple(typed_functions), tuple(typed_machines), macro_ids, temporal_ids)

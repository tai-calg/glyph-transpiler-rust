from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .compiler import (
    BinaryExpr,
    CallExpr,
    ExternDecl,
    Expr,
    FieldExpr,
    FunctionDecl,
    GlyphError,
    NameExpr,
    Param,
    Program,
    TryExpr,
    TypeRef,
    UnaryExpr,
)
from .pattern_codegen import PatternRustGenerator


@dataclass(frozen=True)
class FunctionType:
    params: tuple[TypeRef, ...]
    result: TypeRef


def as_function_type(ty: TypeRef) -> FunctionType | None:
    """Decode `Fn<A,R>` or `Fn<(A,B),R>` into a function-pointer type."""

    if ty.name != "Fn" or len(ty.args) != 2:
        return None
    args_ty, result = ty.args
    if args_ty.name == "tuple":
        params = args_ty.args
    elif args_ty.name == "()":
        params = ()
    else:
        params = (args_ty,)
    return FunctionType(params, result)


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


def _function_exprs(decl: FunctionDecl) -> Iterable[Expr]:
    if decl.expression is not None:
        yield decl.expression
    for clause in decl.guards:
        if clause.condition is not None:
            yield clause.condition
        yield clause.value


def _direct_calls(decl: FunctionDecl) -> set[str]:
    calls: set[str] = set()
    for root in _function_exprs(decl):
        for expr in _walk(root):
            if isinstance(expr, CallExpr) and isinstance(expr.callee, NameExpr):
                calls.add(expr.callee.name)
    return calls


def _signature_type(decl: FunctionDecl) -> FunctionType:
    return FunctionType(tuple(param.ty for param in decl.params), decl.return_type)


def _is_transitively_pure(
    name: str,
    functions: Mapping[str, FunctionDecl],
    externs: set[str],
    memo: dict[str, bool],
    visiting: set[str],
) -> bool:
    if name in memo:
        return memo[name]
    if name in visiting:
        return True
    decl = functions[name]
    calls = _direct_calls(decl)
    if calls & externs:
        memo[name] = False
        return False
    next_visiting = {*visiting, name}
    pure = all(
        callee not in functions
        or _is_transitively_pure(callee, functions, externs, memo, next_visiting)
        for callee in calls
    )
    memo[name] = pure
    return pure


def _validate_fn_type(ty: TypeRef, line: int) -> None:
    if ty.name == "Fn":
        function_ty = as_function_type(ty)
        if function_ty is None:
            raise GlyphError(
                f"{line}行目: 関数値型は Fn<Input,Output> または Fn<(A,B),Output> で記述する"
            )
        for item in (*function_ty.params, function_ty.result):
            if item.name == "Fn":
                raise GlyphError(f"{line}行目: 入れ子のFn型は現在未対応")
    for arg in ty.args:
        _validate_fn_type(arg, line)


def _validate_function_argument(
    caller: FunctionDecl,
    expected: FunctionType,
    actual: Expr,
    functions: Mapping[str, FunctionDecl],
    externs: set[str],
    local_fn_params: Mapping[str, FunctionType],
    purity: Mapping[str, bool],
) -> None:
    if not isinstance(actual, NameExpr):
        raise GlyphError(
            f"{caller.line}行目: Fn引数には名前付き純粋関数またはFn型引数を渡す"
        )
    if actual.name in externs:
        raise GlyphError(
            f"{caller.line}行目: 作用境界 '!{actual.name}' は関数値として渡せない"
        )
    if actual.name in local_fn_params:
        if local_fn_params[actual.name] != expected:
            raise GlyphError(
                f"{caller.line}行目: Fn型引数 '{actual.name}' のシグネチャが一致しない"
            )
        return
    target = functions.get(actual.name)
    if target is None:
        raise GlyphError(
            f"{caller.line}行目: 関数値 '{actual.name}' は純粋関数として定義されていない"
        )
    if not purity.get(actual.name, False):
        raise GlyphError(
            f"{caller.line}行目: 関数 '{actual.name}' は作用境界へ到達するため関数値にできない"
        )
    if _signature_type(target) != expected:
        raise GlyphError(
            f"{caller.line}行目: 関数値 '{actual.name}' のシグネチャがFn型と一致しない"
        )


def validate_function_values(program: Program) -> None:
    """Validate first-class function pointers while keeping effect calls explicit."""

    functions = {
        decl.name: decl
        for decl in program.declarations
        if isinstance(decl, FunctionDecl)
    }
    externs = {
        decl.name for decl in program.declarations if isinstance(decl, ExternDecl)
    }
    purity_memo: dict[str, bool] = {}
    purity = {
        name: _is_transitively_pure(name, functions, externs, purity_memo, set())
        for name in functions
    }

    for decl in program.declarations:
        if isinstance(decl, FunctionDecl):
            for param in decl.params:
                _validate_fn_type(param.ty, decl.line)
            _validate_fn_type(decl.return_type, decl.line)
        elif isinstance(decl, ExternDecl):
            for param in decl.params:
                _validate_fn_type(param.ty, decl.line)
                if as_function_type(param.ty) is not None:
                    raise GlyphError(
                        f"{decl.line}行目: 作用境界 '!{decl.name}' はFn型引数を受け取れない"
                    )
            _validate_fn_type(decl.return_type, decl.line)
            if as_function_type(decl.return_type) is not None:
                raise GlyphError(
                    f"{decl.line}行目: 作用境界 '!{decl.name}' はFn型を返せない"
                )

    for caller in functions.values():
        local_fn_params = {
            param.name: function_ty
            for param in caller.params
            if (function_ty := as_function_type(param.ty)) is not None
        }
        returned_function = as_function_type(caller.return_type)
        if returned_function is not None and caller.expression is not None:
            _validate_function_argument(
                caller,
                returned_function,
                caller.expression,
                functions,
                externs,
                local_fn_params,
                purity,
            )

        for root in _function_exprs(caller):
            for expr in _walk(root):
                if not isinstance(expr, CallExpr) or not isinstance(expr.callee, NameExpr):
                    continue
                callee_name = expr.callee.name

                local_function = local_fn_params.get(callee_name)
                if local_function is not None:
                    if len(expr.args) != len(local_function.params):
                        raise GlyphError(
                            f"{caller.line}行目: Fn型引数 '{callee_name}' は"
                            f"{len(local_function.params)}引数だが{len(expr.args)}引数を受け取った"
                        )
                    continue

                callee = functions.get(callee_name)
                if callee is None or len(expr.args) != len(callee.params):
                    continue
                for param, actual in zip(callee.params, expr.args):
                    expected = as_function_type(param.ty)
                    if expected is None:
                        continue
                    _validate_function_argument(
                        caller,
                        expected,
                        actual,
                        functions,
                        externs,
                        local_fn_params,
                        purity,
                    )


class FunctionalPatternRustGenerator(PatternRustGenerator):
    """Pattern generator extended with Rust function-pointer types."""

    def _type(self, ty: TypeRef) -> str:
        function_ty = as_function_type(ty)
        if function_ty is None:
            return super()._type(ty)
        params = ", ".join(
            PatternRustGenerator._type(self, item) for item in function_ty.params
        )
        result = PatternRustGenerator._type(self, function_ty.result)
        return f"fn({params}) -> {result}"


def function_signature_type(params: Sequence[Param], result: TypeRef) -> TypeRef:
    args = TypeRef("tuple", tuple(param.ty for param in params))
    return TypeRef("Fn", (args, result))

from __future__ import annotations

from collections.abc import Iterable

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
from .temporal import (
    Always,
    And,
    Atom,
    Eventually,
    Formula,
    Implies,
    Not,
    Or,
    SpecDecl,
    Until,
    Within,
)
from .compiler import GlyphError


_PURE_INTRINSICS = {"finite", "min", "max", "Ok", "Err", "Some"}


def _expr_children(expr: Expr) -> tuple[Expr, ...]:
    if isinstance(expr, UnaryExpr):
        return (expr.expr,)
    if isinstance(expr, BinaryExpr):
        return (expr.left, expr.right)
    if isinstance(expr, CallExpr):
        return (expr.callee, *expr.args)
    if isinstance(expr, FieldExpr):
        return (expr.base,)
    if isinstance(expr, TryExpr):
        return (expr.expr,)
    return ()


def _walk_expr(expr: Expr) -> Iterable[Expr]:
    yield expr
    for child in _expr_children(expr):
        yield from _walk_expr(child)


def _formula_children(formula: Formula) -> tuple[Formula, ...]:
    if isinstance(formula, (Not, Always, Eventually, Within)):
        return (formula.value,)
    if isinstance(formula, (And, Or)):
        return (formula.left, formula.right)
    if isinstance(formula, Implies):
        return (formula.premise, formula.consequence)
    if isinstance(formula, Until):
        return (formula.hold, formula.target)
    return ()


def _atoms(formula: Formula) -> Iterable[Atom]:
    if isinstance(formula, Atom):
        yield formula
        return
    for child in _formula_children(formula):
        yield from _atoms(child)


def _call_names(expr: Expr) -> tuple[set[str], bool]:
    names: set[str] = set()
    has_dynamic_call = False
    for node in _walk_expr(expr):
        if not isinstance(node, CallExpr):
            continue
        if isinstance(node.callee, NameExpr):
            names.add(node.callee.name)
        else:
            has_dynamic_call = True
    return names, has_dynamic_call


def _function_expressions(decl: FunctionDecl) -> Iterable[Expr]:
    if decl.expression is not None:
        yield decl.expression
    for guard in decl.guards:
        if guard.condition is not None:
            yield guard.condition
        yield guard.value


def _known_symbols(program: Program) -> tuple[set[str], set[str], dict[str, FunctionDecl]]:
    externs: set[str] = set()
    constructors: set[str] = set(_PURE_INTRINSICS)
    functions: dict[str, FunctionDecl] = {}
    for decl in program.declarations:
        if isinstance(decl, ExternDecl):
            externs.add(decl.name)
        elif isinstance(decl, FunctionDecl):
            functions[decl.name] = decl
        elif isinstance(decl, ProductDecl):
            constructors.add(decl.name)
        elif isinstance(decl, SumDecl):
            constructors.update(variant.name for variant in decl.variants)
    return externs, constructors, functions


def _impure_functions(program: Program) -> tuple[set[str], set[str], set[str]]:
    externs, constructors, functions = _known_symbols(program)
    declared_functions = set(functions)
    safe_names = constructors | declared_functions
    calls: dict[str, set[str]] = {}
    impure: set[str] = set()

    for name, decl in functions.items():
        function_calls: set[str] = set()
        dynamic = False
        for expr in _function_expressions(decl):
            names, has_dynamic_call = _call_names(expr)
            function_calls.update(names)
            dynamic = dynamic or has_dynamic_call
        calls[name] = function_calls
        if dynamic or any(
            called in externs or called not in safe_names for called in function_calls
        ):
            impure.add(name)

    changed = True
    while changed:
        changed = False
        for name, function_calls in calls.items():
            if name not in impure and function_calls & impure:
                impure.add(name)
                changed = True

    return externs, constructors, impure


def validate_temporal_specs(program: Program, specs: Iterable[SpecDecl]) -> None:
    """時相述語が観測だけに依存し、外部作用を起こさないことを検査する。"""
    externs, constructors, impure_functions = _impure_functions(program)
    pure_functions = {
        decl.name
        for decl in program.declarations
        if isinstance(decl, FunctionDecl) and decl.name not in impure_functions
    }
    allowed_calls = constructors | pure_functions

    for spec in specs:
        for atom in _atoms(spec.formula):
            for node in _walk_expr(atom.expr):
                if isinstance(node, TryExpr):
                    raise GlyphError(
                        f"{spec.line}行目: 時相制約 '{spec.name}' の状態述語では "
                        "'?' 失敗伝播を使えない"
                    )
                if not isinstance(node, CallExpr):
                    continue
                if not isinstance(node.callee, NameExpr):
                    raise GlyphError(
                        f"{spec.line}行目: 時相制約 '{spec.name}' の状態述語では "
                        "動的な呼出しを使えない"
                    )
                called = node.callee.name
                if called in externs or called in impure_functions:
                    raise GlyphError(
                        f"{spec.line}行目: 時相制約 '{spec.name}' の状態述語から "
                        f"外部作用を含む '{called}' を呼べない"
                    )
                if called not in allowed_calls:
                    raise GlyphError(
                        f"{spec.line}行目: 時相制約 '{spec.name}' の状態述語で "
                        f"呼出し '{called}' の純粋性を確認できない"
                    )

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from .compiler import (
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    FieldExpr,
    FunctionDecl,
    GlyphError,
    GuardClause,
    NameExpr,
    NumberExpr,
    Program,
    TryExpr,
    UnaryExpr,
    _collect_macros,
    _find_matching,
    _resolve_macros,
    parse_expr,
)
from .machine import MachineDecl


_MAX_AST_MACRO_DEPTH = 64


@dataclass(frozen=True)
class AstMacroDef:
    """A function-like compile-time macro whose body is an expression tree."""

    name: str
    params: tuple[str, ...]
    body: Expr
    line: int


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].rstrip()


def extract_ast_macros(source: str) -> tuple[str, tuple[AstMacroDef, ...]]:
    """Extract `@name(x,y)=expr` without changing source line numbers.

    Object-like `@NAME=expr` macros remain in the source and keep the existing
    token-macro behavior. Function-like macros are parsed into expression trees.
    """

    raw_lines = source.splitlines()
    output = list(raw_lines)
    pending: list[tuple[str, tuple[str, ...], str, int]] = []
    seen: dict[str, int] = {}

    for index, original in enumerate(raw_lines):
        clean = _strip_comment(original)
        if not clean.strip() or clean[0].isspace() or not clean.startswith("@"):
            continue
        body = clean[1:].strip()
        open_pos = body.find("(")
        eq_pos = body.find("=")
        if open_pos <= 0 or (eq_pos >= 0 and eq_pos < open_pos):
            continue

        line = index + 1
        name = body[:open_pos].strip()
        if not name.isidentifier():
            raise GlyphError(f"{line}行目: 不正なASTマクロ名 '{name}'")
        close_pos = _find_matching(body, open_pos)
        rest = body[close_pos + 1 :].strip()
        if not rest.startswith("="):
            raise GlyphError(f"{line}行目: @name(args)=expression の形式が必要")
        expression = rest[1:].strip()
        if not expression:
            raise GlyphError(f"{line}行目: ASTマクロ '{name}' の本体が空")
        if name in seen:
            raise GlyphError(
                f"{line}行目: ASTマクロ '{name}' は{seen[name]}行目で既に定義済み"
            )

        params_text = body[open_pos + 1 : close_pos].strip()
        params: list[str] = []
        if params_text:
            for item in params_text.split(","):
                param = item.strip()
                if not param.isidentifier() or param in {"_", "true", "false"}:
                    raise GlyphError(f"{line}行目: 不正なASTマクロ引数 '{param}'")
                if param in params:
                    raise GlyphError(f"{line}行目: ASTマクロ引数 '{param}' が重複")
                params.append(param)

        pending.append((name, tuple(params), expression, line))
        seen[name] = line
        output[index] = ""

    cleaned = "\n".join(output) + ("\n" if source.endswith("\n") else "")
    token_macros = _resolve_macros(_collect_macros(cleaned.splitlines()))
    definitions = tuple(
        AstMacroDef(name, params, parse_expr(expression, token_macros), line)
        for name, params, expression, line in pending
    )
    return cleaned, definitions


def _substitute(expr: Expr, bindings: Mapping[str, Expr]) -> Expr:
    if isinstance(expr, NameExpr):
        return bindings.get(expr.name, expr)
    if isinstance(expr, (NumberExpr, BoolExpr)):
        return expr
    if isinstance(expr, UnaryExpr):
        return UnaryExpr(expr.op, _substitute(expr.expr, bindings))
    if isinstance(expr, BinaryExpr):
        return BinaryExpr(
            expr.op,
            _substitute(expr.left, bindings),
            _substitute(expr.right, bindings),
        )
    if isinstance(expr, CallExpr):
        return CallExpr(
            _substitute(expr.callee, bindings),
            tuple(_substitute(arg, bindings) for arg in expr.args),
        )
    if isinstance(expr, FieldExpr):
        return FieldExpr(_substitute(expr.base, bindings), expr.field)
    if isinstance(expr, TryExpr):
        return TryExpr(_substitute(expr.expr, bindings))
    raise TypeError(f"unknown expression: {expr!r}")


def expand_expr_macros(
    expr: Expr,
    macros: Mapping[str, AstMacroDef],
    stack: tuple[str, ...] = (),
) -> Expr:
    """Expand function-like macros by substituting AST nodes, not source text."""

    if len(stack) > _MAX_AST_MACRO_DEPTH:
        raise GlyphError(
            f"ASTマクロ展開の深さが上限{_MAX_AST_MACRO_DEPTH}を超えた: "
            + " -> ".join(stack)
        )

    if isinstance(expr, CallExpr) and isinstance(expr.callee, NameExpr):
        macro = macros.get(expr.callee.name)
        if macro is not None:
            if macro.name in stack:
                start = stack.index(macro.name)
                cycle = (*stack[start:], macro.name)
                raise GlyphError(f"AST macro cycle: {' -> '.join(cycle)}")
            if len(expr.args) != len(macro.params):
                raise GlyphError(
                    f"{macro.line}行目: ASTマクロ '{macro.name}' は"
                    f"{len(macro.params)}引数だが{len(expr.args)}引数を受け取った"
                )
            expanded_args = tuple(expand_expr_macros(arg, macros, stack) for arg in expr.args)
            body = _substitute(macro.body, dict(zip(macro.params, expanded_args)))
            return expand_expr_macros(body, macros, (*stack, macro.name))

    if isinstance(expr, (NameExpr, NumberExpr, BoolExpr)):
        return expr
    if isinstance(expr, UnaryExpr):
        return UnaryExpr(expr.op, expand_expr_macros(expr.expr, macros, stack))
    if isinstance(expr, BinaryExpr):
        return BinaryExpr(
            expr.op,
            expand_expr_macros(expr.left, macros, stack),
            expand_expr_macros(expr.right, macros, stack),
        )
    if isinstance(expr, CallExpr):
        return CallExpr(
            expand_expr_macros(expr.callee, macros, stack),
            tuple(expand_expr_macros(arg, macros, stack) for arg in expr.args),
        )
    if isinstance(expr, FieldExpr):
        return FieldExpr(expand_expr_macros(expr.base, macros, stack), expr.field)
    if isinstance(expr, TryExpr):
        return TryExpr(expand_expr_macros(expr.expr, macros, stack))
    raise TypeError(f"unknown expression: {expr!r}")


def expand_program_macros(
    program: Program, definitions: Sequence[AstMacroDef]
) -> Program:
    macros = {definition.name: definition for definition in definitions}
    if not macros:
        return program

    declarations = []
    for decl in program.declarations:
        if not isinstance(decl, FunctionDecl):
            declarations.append(decl)
            continue
        expression = (
            None if decl.expression is None else expand_expr_macros(decl.expression, macros)
        )
        guards = tuple(
            GuardClause(
                None
                if clause.condition is None
                else expand_expr_macros(clause.condition, macros),
                expand_expr_macros(clause.value, macros),
                clause.line,
            )
            for clause in decl.guards
        )
        declarations.append(replace(decl, expression=expression, guards=guards))
    return Program(tuple(declarations))


def expand_function_macros(
    functions: Sequence[FunctionDecl], definitions: Sequence[AstMacroDef]
) -> tuple[FunctionDecl, ...]:
    wrapped = expand_program_macros(Program(tuple(functions)), definitions)
    return tuple(
        decl for decl in wrapped.declarations if isinstance(decl, FunctionDecl)
    )


def expand_machine_macros(
    machines: Sequence[MachineDecl], definitions: Sequence[AstMacroDef]
) -> tuple[MachineDecl, ...]:
    macros = {definition.name: definition for definition in definitions}
    if not macros:
        return tuple(machines)
    return tuple(
        replace(
            machine,
            selector=expand_expr_macros(machine.selector, macros),
            initial=expand_expr_macros(machine.initial, macros),
            next_expr=expand_expr_macros(machine.next_expr, macros),
        )
        for machine in machines
    )

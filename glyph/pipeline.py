from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Iterable, Mapping, Sequence

from .compiler import (
    AliasDecl,
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    GlyphError,
    NameExpr,
    NumberExpr,
    Param,
    ProductDecl,
    Program,
    SumDecl,
    TryExpr,
    TypeRef,
    UnaryExpr,
    _find_top_level_char,
    _parse_named_signature,
    parse_expr,
    parse_program,
    parse_type,
)


@dataclass(frozen=True)
class CallableSignature:
    name: str
    params: tuple[Param, ...]
    result: TypeRef
    effect: bool
    line: int


@dataclass(frozen=True)
class LambdaLowering:
    name: str
    line: int
    parameter: str
    parameter_type: TypeRef
    result_type: TypeRef
    body: str


@dataclass(frozen=True)
class PipelineLoweringResult:
    source: str
    lambdas: tuple[LambdaLowering, ...]


_BUILTINS = {"min", "max", "finite", "Ok", "Err"}
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _strip_comment(line: str) -> tuple[str, str]:
    index = line.find("#")
    if index < 0:
        return line.rstrip(), ""
    return line[:index].rstrip(), line[index:]


def join_pipeline_continuations(source: str) -> str:
    """Join a visual `/>` chain while preserving the original line count.

    Both forms are accepted:

    ```glyph
    >run(x:U):U=x
      /> inc
      /> |n| n*2
    ```

    and

    ```glyph
    >run(x:U):U=
      x
      /> inc
    ```
    """

    lines = source.splitlines()
    output = list(lines)
    index = 0
    while index < len(lines):
        code, comment = _strip_comment(lines[index])
        stripped = code.strip()
        if code[:1].isspace() or not stripped.startswith((">", "!")):
            index += 1
            continue
        equal = _find_top_level_char(stripped, "=")
        if equal < 0:
            index += 1
            continue

        body = stripped[equal + 1 :].strip()
        fragments: list[str] = [body] if body else []
        consumed: list[int] = []
        cursor = index + 1
        need_initial = not body
        while cursor < len(lines):
            next_code, _ = _strip_comment(lines[cursor])
            if not next_code.strip():
                cursor += 1
                continue
            if not next_code[:1].isspace():
                break
            item = next_code.strip()
            if need_initial:
                if item.startswith("/>"):
                    raise GlyphError(
                        f"{cursor + 1}行目: パイプラインの最初に入力式が必要"
                    )
                fragments.append(item)
                consumed.append(cursor)
                need_initial = False
                cursor += 1
                continue
            if not item.startswith("/>"):
                break
            fragments.append(item)
            consumed.append(cursor)
            cursor += 1

        if consumed:
            prefix = stripped[: equal + 1]
            joined = prefix + " ".join(fragment for fragment in fragments if fragment)
            output[index] = joined + ((" " + comment) if comment else "")
            for consumed_index in consumed:
                output[consumed_index] = ""
            index = cursor
        else:
            index += 1

    return "\n".join(output) + ("\n" if source.endswith("\n") else "")


def _split_pipeline(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    round_depth = 0
    brace_depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "(":
            round_depth += 1
        elif char == ")":
            round_depth -= 1
        elif char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
        elif (
            char == "/"
            and index + 1 < len(text)
            and text[index + 1] == ">"
            and round_depth == 0
            and brace_depth == 0
        ):
            parts.append(text[start:index].strip())
            start = index + 2
            index += 2
            continue
        index += 1
    parts.append(text[start:].strip())
    if any(not part for part in parts):
        raise GlyphError(f"空のパイプライン段がある: {text}")
    return parts


def _render_type(ty: TypeRef) -> str:
    if not ty.args:
        return ty.name
    return f"{ty.name}<{','.join(_render_type(arg) for arg in ty.args)}>"


def _collect_signatures(lines: Sequence[str]) -> dict[str, CallableSignature]:
    signatures: dict[str, CallableSignature] = {}
    for line_number, original in enumerate(lines, start=1):
        code, _ = _strip_comment(original)
        stripped = code.strip()
        if code[:1].isspace() or not stripped.startswith((">", "!")):
            continue
        name, params, result, _ = _parse_named_signature(stripped[1:].strip(), line_number)
        signatures[name] = CallableSignature(
            name,
            params,
            result,
            stripped.startswith("!"),
            line_number,
        )
    return signatures


def _collect_types(lines: Sequence[str]) -> tuple[
    dict[str, ProductDecl], dict[str, str], set[str]
]:
    declarations = []
    for original in lines:
        code, _ = _strip_comment(original)
        stripped = code.strip()
        if not code[:1].isspace() and stripped.startswith(("*", "+", "=")):
            declarations.append(stripped)
    if not declarations:
        return {}, {}, set()
    parsed = parse_program("\n".join(declarations))
    products = {
        declaration.name: declaration
        for declaration in parsed.declarations
        if isinstance(declaration, ProductDecl)
    }
    variants: dict[str, str] = {}
    type_names: set[str] = set()
    for declaration in parsed.declarations:
        if isinstance(declaration, (ProductDecl, SumDecl, AliasDecl)):
            type_names.add(declaration.name)
        if isinstance(declaration, SumDecl):
            for variant in declaration.variants:
                variants[variant.name] = declaration.name
    return products, variants, type_names


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


def _unwrap_result(ty: TypeRef) -> TypeRef | None:
    if ty.name == "R" and len(ty.args) == 2:
        return ty.args[0]
    return None


def _compatible(actual: TypeRef | None, expected: TypeRef) -> bool:
    return actual is None or actual == expected


def _infer_expr_type(
    expr: Expr,
    locals_: Mapping[str, TypeRef],
    signatures: Mapping[str, CallableSignature],
    products: Mapping[str, ProductDecl],
    variants: Mapping[str, str],
    expected: TypeRef | None = None,
) -> TypeRef | None:
    if isinstance(expr, NameExpr):
        if expr.name in locals_:
            return locals_[expr.name]
        if expr.name in variants:
            return TypeRef(variants[expr.name])
        return expected
    if isinstance(expr, NumberExpr):
        return expected
    if isinstance(expr, BoolExpr):
        return TypeRef("bool")
    if isinstance(expr, UnaryExpr):
        if expr.op == "!":
            return TypeRef("bool")
        return _infer_expr_type(
            expr.expr, locals_, signatures, products, variants, expected
        )
    if isinstance(expr, BinaryExpr):
        if expr.op in {"|", "&", "==", "!=", "<", ">", "<=", ">="}:
            return TypeRef("bool")
        left = _infer_expr_type(
            expr.left, locals_, signatures, products, variants, expected
        )
        right = _infer_expr_type(
            expr.right, locals_, signatures, products, variants, left or expected
        )
        return left or right or expected
    if isinstance(expr, FieldExpr):
        base = _infer_expr_type(
            expr.base, locals_, signatures, products, variants, None
        )
        product = products.get(base.name) if base is not None else None
        if product is None:
            return expected
        return next(
            (field.ty for field in product.fields if field.name == expr.field), expected
        )
    if isinstance(expr, TryExpr):
        inner = _infer_expr_type(
            expr.expr, locals_, signatures, products, variants, None
        )
        return _unwrap_result(inner) if inner is not None else expected
    if isinstance(expr, CallExpr) and isinstance(expr.callee, NameExpr):
        name = expr.callee.name
        signature = signatures.get(name)
        if signature is not None:
            return signature.result
        if name in products:
            return TypeRef(name)
        if name in variants:
            return TypeRef(variants[name])
        if name in {"min", "max"} and expr.args:
            return _infer_expr_type(
                expr.args[0], locals_, signatures, products, variants, expected
            )
        if name == "finite":
            return TypeRef("bool")
        if name in {"Ok", "Err"}:
            return expected
    return expected


def _parse_lambda(stage: str, line: int) -> tuple[str, TypeRef | None, str]:
    if not stage.startswith("|"):
        raise GlyphError(f"{line}行目: ラムダ式は |x| expression の形式で記述する")
    close = stage.find("|", 1)
    if close < 0:
        raise GlyphError(f"{line}行目: ラムダ式の2つ目の '|' がない")
    header = stage[1:close].strip()
    body = stage[close + 1 :].strip()
    if not body:
        raise GlyphError(f"{line}行目: ラムダ式の本体が空")
    params = [part.strip() for part in header.split(",") if part.strip()]
    if len(params) != 1:
        raise GlyphError(
            f"{line}行目: `/>`内のラムダは現在1引数だけを受け取る"
        )
    item = params[0]
    if ":" in item:
        name, type_text = (part.strip() for part in item.split(":", 1))
        parameter_type = parse_type(type_text)
    else:
        name = item
        parameter_type = None
    if not _NAME_RE.match(name):
        raise GlyphError(f"{line}行目: 不正なラムダ引数名 '{name}'")
    return name, parameter_type, body


def _free_names(expr: Expr) -> set[str]:
    return {item.name for item in _walk(expr) if isinstance(item, NameExpr)}


def _collect_macro_names(lines: Sequence[str]) -> set[str]:
    names: set[str] = set()
    for original in lines:
        code, _ = _strip_comment(original)
        stripped = code.strip()
        if code[:1].isspace() or not stripped.startswith("@"):
            continue
        body = stripped[1:]
        stop = min(
            (index for index in (body.find("="), body.find("(")) if index >= 0),
            default=-1,
        )
        if stop > 0:
            names.add(body[:stop].strip())
    return names


def _impure_functions(
    lines: Sequence[str], signatures: Mapping[str, CallableSignature]
) -> set[str]:
    effects = {name for name, signature in signatures.items() if signature.effect}
    bodies: dict[str, str] = {}
    for line_number, original in enumerate(lines, start=1):
        code, _ = _strip_comment(original)
        stripped = code.strip()
        if code[:1].isspace() or not stripped.startswith(">"):
            continue
        name, _, _, body = _parse_named_signature(stripped[1:].strip(), line_number)
        if body is not None:
            bodies[name] = body
    impure = set(effects)
    changed = True
    while changed:
        changed = False
        for name, body in bodies.items():
            if name in impure:
                continue
            if any(re.search(rf"\b{re.escape(target)}\s*\(", body) for target in impure):
                impure.add(name)
                changed = True
    return impure


def lower_lambda_pipelines(source: str) -> PipelineLoweringResult:
    """Lower `value /> stage /> |x| expr` to ordinary named calls.

    The parser and Rust backend therefore keep one expression model. Synthetic
    lambda functions are given their original source line after parsing.
    """

    lines = source.splitlines()
    signatures = _collect_signatures(lines)
    products, variants, type_names = _collect_types(lines)
    macro_names = _collect_macro_names(lines)
    impure = _impure_functions(lines, signatures)
    all_global_names = {
        *signatures,
        *products,
        *variants,
        *type_names,
        *macro_names,
        *_BUILTINS,
    }
    output = list(lines)
    lowerings: list[LambdaLowering] = []
    lambda_index = 0

    for line_number, original in enumerate(lines, start=1):
        code, comment = _strip_comment(original)
        stripped = code.strip()
        if code[:1].isspace() or not stripped.startswith((">", "!")):
            continue
        marker = stripped[0]
        name, params, result_type, body = _parse_named_signature(
            stripped[1:].strip(), line_number
        )
        if body is None or "/>" not in body:
            continue
        parts = _split_pipeline(body)
        current_text = parts[0]
        local_types = {parameter.name: parameter.ty for parameter in params}
        try:
            current_expr = parse_expr(current_text)
        except GlyphError as exc:
            raise GlyphError(f"{line_number}行目: パイプライン入力: {exc}") from exc
        current_type = _infer_expr_type(
            current_expr, local_types, signatures, products, variants, None
        )

        for stage_index, stage in enumerate(parts[1:]):
            final_stage = stage_index == len(parts[1:]) - 1
            if stage.startswith("|"):
                parameter, explicit_type, lambda_body = _parse_lambda(stage, line_number)
                parameter_type = explicit_type or current_type
                if parameter_type is None:
                    raise GlyphError(
                        f"{line_number}行目: ラムダ引数 '{parameter}' の型を推論できない。"
                        f" |{parameter}:Type| と注釈する"
                    )
                if current_type is not None and explicit_type is not None and current_type != explicit_type:
                    raise GlyphError(
                        f"{line_number}行目: パイプ値の型 {_render_type(current_type)} を"
                        f"ラムダ引数 {_render_type(explicit_type)} へ渡せない"
                    )
                try:
                    body_expr = parse_expr(lambda_body)
                except GlyphError as exc:
                    raise GlyphError(f"{line_number}行目: ラムダ本体: {exc}") from exc

                free = _free_names(body_expr) - {parameter} - all_global_names
                captured = free & set(local_types)
                if captured:
                    names = ", ".join(sorted(captured))
                    raise GlyphError(
                        f"{line_number}行目: non-capturingラムダが外側の変数を捕捉している: {names}"
                    )
                unknown = {name for name in free if not name[:1].isupper()}
                if unknown:
                    names = ", ".join(sorted(unknown))
                    raise GlyphError(
                        f"{line_number}行目: ラムダ本体に未解決名がある: {names}"
                    )
                called = {
                    item.callee.name
                    for item in _walk(body_expr)
                    if isinstance(item, CallExpr)
                    and isinstance(item.callee, NameExpr)
                }
                bad_calls = called & impure
                if bad_calls:
                    names = ", ".join(sorted(bad_calls))
                    raise GlyphError(
                        f"{line_number}行目: ラムダは純粋でなければならない。作用へ到達する: {names}"
                    )

                expected_result = result_type if final_stage else None
                body_type = _infer_expr_type(
                    body_expr,
                    {parameter: parameter_type},
                    signatures,
                    products,
                    variants,
                    expected_result,
                )
                if body_type is None:
                    raise GlyphError(
                        f"{line_number}行目: ラムダ戻り型を推論できない。"
                        " 本体または後続段を明確にする"
                    )
                synthetic = f"__glyph_lambda_L{line_number}_{lambda_index}"
                lambda_index += 1
                lowerings.append(
                    LambdaLowering(
                        synthetic,
                        line_number,
                        parameter,
                        parameter_type,
                        body_type,
                        lambda_body,
                    )
                )
                signatures[synthetic] = CallableSignature(
                    synthetic,
                    (Param(parameter, parameter_type),),
                    body_type,
                    False,
                    line_number,
                )
                current_text = f"{synthetic}({current_text})"
                current_type = body_type
                continue

            propagates = stage.endswith("?")
            callable_name = stage[:-1].strip() if propagates else stage.strip()
            if not _NAME_RE.match(callable_name):
                raise GlyphError(
                    f"{line_number}行目: `/>`段は関数名、関数名?、またはラムダ式にする: {stage}"
                )
            signature = signatures.get(callable_name)
            if signature is None:
                raise GlyphError(
                    f"{line_number}行目: パイプライン関数 '{callable_name}' が未定義"
                )
            if len(signature.params) != 1:
                raise GlyphError(
                    f"{line_number}行目: `/> {callable_name}` は1引数関数でなければならない"
                )
            expected_input = signature.params[0].ty
            if not _compatible(current_type, expected_input):
                raise GlyphError(
                    f"{line_number}行目: {_render_type(current_type)} を"
                    f"{callable_name}({_render_type(expected_input)})へ渡せない"
                )
            current_text = f"{callable_name}({current_text})" + ("?" if propagates else "")
            if propagates:
                unwrapped = _unwrap_result(signature.result)
                if unwrapped is None:
                    raise GlyphError(
                        f"{line_number}行目: '/> {callable_name}?' の戻り型はResultでなければならない"
                    )
                current_type = unwrapped
            else:
                current_type = signature.result

        prefix = stripped[: stripped.find("=") + 1]
        rewritten = prefix + current_text
        output[line_number - 1] = rewritten + ((" " + comment) if comment else "")

    if lowerings:
        output.append("")
        output.append("# generated non-capturing lambdas")
        for lowering in lowerings:
            output.append(
                f">{lowering.name}({lowering.parameter}:{_render_type(lowering.parameter_type)})"
                f":{_render_type(lowering.result_type)}={lowering.body}"
            )

    return PipelineLoweringResult(
        "\n".join(output) + ("\n" if source.endswith("\n") else ""),
        tuple(lowerings),
    )


def restore_lambda_source_lines(
    program: Program, lowerings: Sequence[LambdaLowering]
) -> Program:
    lines = {lowering.name: lowering.line for lowering in lowerings}
    if not lines:
        return program
    declarations = []
    for declaration in program.declarations:
        if isinstance(declaration, FunctionDecl) and declaration.name in lines:
            declarations.append(replace(declaration, line=lines[declaration.name]))
        else:
            declarations.append(declaration)
    return Program(tuple(declarations))

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from .ast_macros import AstMacroDef, expand_expr_macros
from .compiler import (
    BinaryExpr,
    CallExpr,
    Expr,
    FunctionDecl,
    GlyphError,
    NameExpr,
    NumberExpr,
    Param,
    ProductDecl,
    Program,
    SumDecl,
    TypeRef,
    UnaryExpr,
    _collect_macros,
    _parse_named_signature,
    _resolve_macros,
    parse_expr,
    parse_program,
)
from .pipeline import (
    CallableSignature,
    LambdaLowering,
    _BUILTINS,
    _NAME_RE,
    _collect_macro_names,
    _collect_signatures,
    _collect_types,
    _compatible,
    _free_names,
    _impure_functions,
    _infer_expr_type,
    _parse_lambda,
    _render_type,
    _split_pipeline,
    _unwrap_result,
    _walk,
)


@dataclass(frozen=True)
class BlockBindingLowering:
    name: str
    type_ref: TypeRef
    line: int
    kind: str
    source: str
    value_helper: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": _render_type(self.type_ref),
            "line": self.line,
            "kind": self.kind,
            "source": self.source,
            "value_helper": self.value_helper,
        }


@dataclass(frozen=True)
class FunctionBlockLowering:
    name: str
    line: int
    bindings: tuple[BlockBindingLowering, ...]
    final_source: str
    final_line: int
    final_helper: str
    continuation_helpers: tuple[str, ...]

    @property
    def helper_names(self) -> tuple[str, ...]:
        return (
            *(binding.value_helper for binding in self.bindings),
            self.final_helper,
            *self.continuation_helpers,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "line": self.line,
            "bindings": [binding.to_dict() for binding in self.bindings],
            "final": {"source": self.final_source, "line": self.final_line},
            "final_helper": self.final_helper,
            "continuation_helpers": list(self.continuation_helpers),
        }


@dataclass(frozen=True)
class FunctionBlockLoweringResult:
    source: str
    blocks: tuple[FunctionBlockLowering, ...]
    lambdas: tuple[LambdaLowering, ...]


@dataclass(frozen=True)
class _RawBinding:
    name: str
    kind: str
    source: str
    line: int
    guards: tuple[tuple[str | None, str, int], ...] = ()


def _split_comment(line: str) -> tuple[str, str]:
    marker = line.find("#")
    if marker < 0:
        return line.rstrip(), ""
    return line[:marker].rstrip(), line[marker:]


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _render_params(params: Sequence[Param]) -> str:
    return ",".join(f"{param.name}:{_render_type(param.ty)}" for param in params)


def _render_call(name: str, arguments: Sequence[str]) -> str:
    return f"{name}({','.join(arguments)})"


def _type_program(lines: Sequence[str]) -> Program:
    declarations: list[str] = []
    for original in lines:
        code, _ = _split_comment(original)
        stripped = code.strip()
        if not code[:1].isspace() and stripped.startswith(("*", "+", "=")):
            declarations.append(stripped)
    return parse_program("\n".join(declarations)) if declarations else Program(())


def _variant_definitions(program: Program) -> dict[str, tuple[str, object]]:
    result: dict[str, tuple[str, object]] = {}
    for declaration in program.declarations:
        if isinstance(declaration, SumDecl):
            for variant in declaration.variants:
                result[variant.name] = (declaration.name, variant)
    return result


def _parse_for_inference(
    text: str,
    token_macros: Mapping[str, tuple[object, ...]],
    ast_macros: Mapping[str, AstMacroDef],
) -> Expr:
    expression = parse_expr(text, token_macros)
    return expand_expr_macros(expression, ast_macros) if ast_macros else expression


def _infer(
    expr: Expr,
    locals_: Mapping[str, TypeRef],
    signatures: Mapping[str, CallableSignature],
    products: Mapping[str, ProductDecl],
    variants: Mapping[str, str],
    expected: TypeRef | None = None,
    *,
    default_numbers: bool = False,
) -> TypeRef | None:
    inferred = _infer_expr_type(expr, locals_, signatures, products, variants, expected)
    if inferred is not None:
        return inferred
    if isinstance(expr, NumberExpr) and default_numbers:
        return TypeRef("f32" if "." in expr.value else "i32")
    if isinstance(expr, UnaryExpr):
        return _infer(
            expr.expr,
            locals_,
            signatures,
            products,
            variants,
            expected,
            default_numbers=default_numbers,
        )
    if isinstance(expr, BinaryExpr):
        if expr.op in {"|", "&", "==", "!=", "<", ">", "<=", ">="}:
            return TypeRef("bool")
        left = _infer(
            expr.left,
            locals_,
            signatures,
            products,
            variants,
            expected,
            default_numbers=default_numbers,
        )
        right = _infer(
            expr.right,
            locals_,
            signatures,
            products,
            variants,
            left or expected,
            default_numbers=default_numbers,
        )
        return left or right or expected
    return expected


def _pattern_binders(
    condition: Expr,
    locals_: Mapping[str, TypeRef],
    variant_defs: Mapping[str, tuple[str, object]],
    global_names: set[str],
) -> dict[str, TypeRef]:
    if not isinstance(condition, BinaryExpr) or condition.op != "==":
        return {}
    right = condition.right
    if isinstance(right, NameExpr):
        variant_name = right.name
        args: tuple[Expr, ...] = ()
    elif isinstance(right, CallExpr) and isinstance(right.callee, NameExpr):
        variant_name = right.callee.name
        args = right.args
    else:
        return {}
    resolved = variant_defs.get(variant_name)
    if resolved is None:
        return {}
    _, variant = resolved
    field_types = (
        tuple(field.ty for field in variant.fields)
        if variant.fields
        else tuple(variant.tuple_types)
    )
    if len(args) != len(field_types):
        return {}
    binders: dict[str, TypeRef] = {}
    for argument, type_ref in zip(args, field_types):
        if not isinstance(argument, NameExpr) or argument.name == "_":
            continue
        if argument.name in locals_ or argument.name in global_names:
            continue
        binders[argument.name] = type_ref
    return binders


def _infer_guard_result(
    guards: Sequence[tuple[str | None, str, int]],
    locals_: Mapping[str, TypeRef],
    signatures: Mapping[str, CallableSignature],
    products: Mapping[str, ProductDecl],
    variants: Mapping[str, str],
    variant_defs: Mapping[str, tuple[str, object]],
    global_names: set[str],
    token_macros: Mapping[str, tuple[object, ...]],
    ast_macros: Mapping[str, AstMacroDef],
) -> TypeRef:
    fallback = [index for index, (condition, _, _) in enumerate(guards) if condition is None]
    if len(fallback) != 1 or fallback[0] != len(guards) - 1:
        line = guards[0][2] if guards else 0
        raise GlyphError(
            f"{line}行目: `:=`の条件ブロックは最後にちょうど1個の '_' 節を持つ"
        )

    parsed: list[tuple[Expr, dict[str, TypeRef], int]] = []
    known: list[TypeRef] = []
    for condition_text, value_text, line in guards:
        condition = (
            None
            if condition_text is None
            else _parse_for_inference(condition_text, token_macros, ast_macros)
        )
        binders = (
            {}
            if condition is None
            else _pattern_binders(condition, locals_, variant_defs, global_names)
        )
        value = _parse_for_inference(value_text, token_macros, ast_macros)
        branch_type = _infer(
            value,
            {**locals_, **binders},
            signatures,
            products,
            variants,
            None,
            default_numbers=False,
        )
        if branch_type is not None and branch_type not in known:
            known.append(branch_type)
        parsed.append((value, binders, line))

    if len(known) > 1:
        rendered = ", ".join(_render_type(item) for item in known)
        raise GlyphError(
            f"{parsed[0][2]}行目: `:=`条件ブロックの分岐型が一致しない: {rendered}"
        )
    expected = known[0] if known else None
    resolved: TypeRef | None = expected
    for value, binders, line in parsed:
        branch_type = _infer(
            value,
            {**locals_, **binders},
            signatures,
            products,
            variants,
            expected,
            default_numbers=True,
        )
        if branch_type is None:
            raise GlyphError(f"{line}行目: `:=`条件ブロックの値型を推論できない")
        if resolved is None:
            resolved = branch_type
            expected = branch_type
        elif branch_type != resolved:
            raise GlyphError(
                f"{line}行目: `:=`条件ブロックは{_render_type(resolved)}を期待するが"
                f"{_render_type(branch_type)}を返す"
            )
    assert resolved is not None
    return resolved


def _lower_pipeline(
    text: str,
    line: int,
    locals_: Mapping[str, TypeRef],
    expected: TypeRef | None,
    signatures: dict[str, CallableSignature],
    products: Mapping[str, ProductDecl],
    variants: Mapping[str, str],
    global_names: set[str],
    impure: set[str],
    token_macros: Mapping[str, tuple[object, ...]],
    ast_macros: Mapping[str, AstMacroDef],
    lambda_counter: list[int],
) -> tuple[str, TypeRef, list[LambdaLowering], list[str]]:
    if "/>" not in text:
        expression = _parse_for_inference(text, token_macros, ast_macros)
        inferred = _infer(
            expression,
            locals_,
            signatures,
            products,
            variants,
            expected,
            default_numbers=True,
        )
        if inferred is None:
            raise GlyphError(f"{line}行目: `:=`右辺の型を推論できない: {text}")
        return text, inferred, [], []

    parts = _split_pipeline(text)
    current_text = parts[0]
    current_expr = _parse_for_inference(current_text, token_macros, ast_macros)
    current_type = _infer(
        current_expr,
        locals_,
        signatures,
        products,
        variants,
        None,
        default_numbers=True,
    )
    lowerings: list[LambdaLowering] = []
    definitions: list[str] = []

    for stage_index, stage in enumerate(parts[1:]):
        final_stage = stage_index == len(parts[1:]) - 1
        if stage.startswith("|"):
            parameter, explicit_type, lambda_body = _parse_lambda(stage, line)
            parameter_type = explicit_type or current_type
            if parameter_type is None:
                raise GlyphError(
                    f"{line}行目: ラムダ引数 '{parameter}' の型を推論できない。"
                    f" |{parameter}:Type| と注釈する"
                )
            if current_type is not None and explicit_type is not None and current_type != explicit_type:
                raise GlyphError(
                    f"{line}行目: パイプ値の型 {_render_type(current_type)} を"
                    f"ラムダ引数 {_render_type(explicit_type)} へ渡せない"
                )
            body_expr = _parse_for_inference(lambda_body, token_macros, ast_macros)
            free = _free_names(body_expr) - {parameter} - global_names
            captured = free & set(locals_)
            if captured:
                names = ", ".join(sorted(captured))
                raise GlyphError(
                    f"{line}行目: non-capturingラムダが外側の変数を捕捉している: {names}"
                )
            unknown = {name for name in free if not name[:1].isupper()}
            if unknown:
                names = ", ".join(sorted(unknown))
                raise GlyphError(f"{line}行目: ラムダ本体に未解決名がある: {names}")
            called = {
                item.callee.name
                for item in _walk(body_expr)
                if isinstance(item, CallExpr) and isinstance(item.callee, NameExpr)
            }
            bad_calls = called & impure
            if bad_calls:
                names = ", ".join(sorted(bad_calls))
                raise GlyphError(
                    f"{line}行目: ラムダは純粋でなければならない。作用へ到達する: {names}"
                )
            body_type = _infer(
                body_expr,
                {parameter: parameter_type},
                signatures,
                products,
                variants,
                expected if final_stage else None,
                default_numbers=True,
            )
            if body_type is None:
                raise GlyphError(f"{line}行目: ラムダ戻り型を推論できない")
            synthetic = f"__glyph_block_lambda_L{line}_{lambda_counter[0]}"
            lambda_counter[0] += 1
            lowering = LambdaLowering(
                synthetic, line, parameter, parameter_type, body_type, lambda_body
            )
            lowerings.append(lowering)
            signatures[synthetic] = CallableSignature(
                synthetic,
                (Param(parameter, parameter_type),),
                body_type,
                False,
                line,
            )
            definitions.append(
                f">{synthetic}({parameter}:{_render_type(parameter_type)}):"
                f"{_render_type(body_type)}={lambda_body}"
            )
            current_text = f"{synthetic}({current_text})"
            current_type = body_type
            continue

        propagates = stage.endswith("?")
        callable_name = stage[:-1].strip() if propagates else stage.strip()
        if not _NAME_RE.match(callable_name):
            raise GlyphError(
                f"{line}行目: `/>`段は関数名、関数名?、またはラムダ式にする: {stage}"
            )
        signature = signatures.get(callable_name)
        if signature is None:
            raise GlyphError(f"{line}行目: パイプライン関数 '{callable_name}' が未定義")
        if len(signature.params) != 1:
            raise GlyphError(
                f"{line}行目: `/> {callable_name}` は1引数関数でなければならない"
            )
        expected_input = signature.params[0].ty
        if not _compatible(current_type, expected_input):
            raise GlyphError(
                f"{line}行目: {_render_type(current_type)} を"
                f"{callable_name}({_render_type(expected_input)})へ渡せない"
            )
        current_text = f"{callable_name}({current_text})" + ("?" if propagates else "")
        current_type = _unwrap_result(signature.result) if propagates else signature.result
        if current_type is None:
            raise GlyphError(
                f"{line}行目: '/> {callable_name}?' の戻り型はResultでなければならない"
            )

    if expected is not None and current_type != expected:
        raise GlyphError(
            f"{line}行目: パイプラインは{_render_type(expected)}を期待するが"
            f"{_render_type(current_type)}を返す"
        )
    if current_type is None:
        raise GlyphError(f"{line}行目: パイプラインの戻り型を推論できない")
    return current_text, current_type, lowerings, definitions


def _parse_block(
    lines: Sequence[str], start: int, end: int, base_indent: int
) -> tuple[list[_RawBinding], str, int, set[int]]:
    bindings: list[_RawBinding] = []
    consumed: set[int] = set()
    final_source: str | None = None
    final_line = 0
    index = start

    while index < end:
        code, _ = _split_comment(lines[index])
        if not code.strip():
            consumed.add(index)
            index += 1
            continue
        if _indent_width(code) != base_indent:
            raise GlyphError(f"{index + 1}行目: 関数ブロックの文は同じインデントに揃える")
        stripped = code.strip()
        assign = stripped.find(":=")
        if assign >= 0:
            if final_source is not None:
                raise GlyphError(f"{index + 1}行目: 最終式の後ろに`:=`定義は書けない")
            name = stripped[:assign].strip()
            rhs = stripped[assign + 2 :].strip()
            if not name.isidentifier() or name in {"_", "true", "false"}:
                raise GlyphError(f"{index + 1}行目: 不正な中間値名 '{name}'")
            binding_line = index + 1
            child_index = index + 1
            children: list[tuple[str, int]] = []
            while child_index < end:
                child_code, _ = _split_comment(lines[child_index])
                if not child_code.strip():
                    consumed.add(child_index)
                    child_index += 1
                    continue
                if _indent_width(child_code) <= base_indent:
                    break
                children.append((child_code.strip(), child_index + 1))
                consumed.add(child_index)
                child_index += 1

            if rhs:
                if children:
                    if any(not item.startswith("/>") for item, _ in children):
                        raise GlyphError(
                            f"{children[0][1]}行目: 同じ行の`:=`右辺には`/>`継続だけを書ける"
                        )
                    rhs = " ".join([rhs, *(item for item, _ in children)])
                bindings.append(_RawBinding(name, "expression", rhs, binding_line))
            else:
                if not children:
                    raise GlyphError(f"{binding_line}行目: ':=' の右辺または条件ブロックが必要")
                if all("=>" in item for item, _ in children):
                    guards: list[tuple[str | None, str, int]] = []
                    for item, line in children:
                        condition_text, value_text = item.split("=>", 1)
                        condition_text = condition_text.strip()
                        value_text = value_text.strip()
                        if not value_text:
                            raise GlyphError(f"{line}行目: '=>' の後ろに値が必要")
                        guards.append(
                            (None if condition_text == "_" else condition_text, value_text, line)
                        )
                    bindings.append(
                        _RawBinding(
                            name,
                            "conditional",
                            "\n".join(item for item, _ in children),
                            binding_line,
                            tuple(guards),
                        )
                    )
                else:
                    first, *rest = children
                    if any(not item.startswith("/>") for item, _ in rest):
                        raise GlyphError(
                            f"{binding_line}行目: 複数行の`:=`式は最初の式の後ろを`/>`で連結する"
                        )
                    rhs = " ".join([first[0], *(item for item, _ in rest)])
                    bindings.append(_RawBinding(name, "expression", rhs, binding_line))
            consumed.add(index)
            index = child_index
            continue

        if final_source is not None:
            raise GlyphError(f"{index + 1}行目: 関数ブロックの最終式は1つだけにする")
        fragments = [stripped]
        consumed.add(index)
        cursor = index + 1
        while cursor < end:
            next_code, _ = _split_comment(lines[cursor])
            if not next_code.strip():
                consumed.add(cursor)
                cursor += 1
                continue
            if _indent_width(next_code) != base_indent:
                raise GlyphError(f"{cursor + 1}行目: 最終式のインデントが不正")
            item = next_code.strip()
            if not item.startswith("/>"):
                raise GlyphError(f"{cursor + 1}行目: 最終式の後ろには`/>`継続しか書けない")
            fragments.append(item)
            consumed.add(cursor)
            cursor += 1
        final_source = " ".join(fragments)
        final_line = index + 1
        index = cursor

    if not bindings:
        raise GlyphError(f"{start + 1}行目: `:=`を含まない本体は従来のガード関数として書く")
    if final_source is None:
        raise GlyphError(f"{start + 1}行目: 関数ブロックの最後に返す式が必要")
    return bindings, final_source, final_line, consumed


def lower_function_blocks(
    source: str,
    ast_macro_definitions: Sequence[AstMacroDef] = (),
) -> FunctionBlockLoweringResult:
    """Lower immutable `:=` blocks while preserving single evaluation."""

    lines = source.splitlines()
    output = list(lines)
    signatures = _collect_signatures(lines)
    products, variants, type_names = _collect_types(lines)
    variant_defs = _variant_definitions(_type_program(lines))
    token_macros = _resolve_macros(_collect_macros(lines))
    ast_macros = {item.name: item for item in ast_macro_definitions}
    macro_names = _collect_macro_names(lines)
    impure = _impure_functions(lines, signatures)
    global_names = {
        *signatures,
        *products,
        *variants,
        *type_names,
        *macro_names,
        *_BUILTINS,
    }

    blocks: list[FunctionBlockLowering] = []
    block_lambdas: list[LambdaLowering] = []
    generated: list[str] = []
    lambda_counter = [0]
    index = 0

    while index < len(lines):
        code, comment = _split_comment(lines[index])
        stripped = code.strip()
        if code[:1].isspace() or not stripped.startswith(">"):
            index += 1
            continue
        line = index + 1
        name, params, return_type, inline = _parse_named_signature(stripped[1:].strip(), line)
        if inline is not None:
            index += 1
            continue

        end = index + 1
        while end < len(lines):
            next_code, _ = _split_comment(lines[end])
            if next_code.strip() and not next_code[:1].isspace():
                break
            end += 1
        significant = [
            (_indent_width(_split_comment(lines[pos])[0]), pos)
            for pos in range(index + 1, end)
            if _split_comment(lines[pos])[0].strip()
        ]
        if not significant:
            index = end
            continue
        base_indent = min(indent for indent, _ in significant)
        base_items = [
            _split_comment(lines[pos])[0].strip()
            for indent, pos in significant
            if indent == base_indent
        ]
        if not any(":=" in item for item in base_items):
            index = end
            continue

        raw_bindings, final_source, final_line, consumed = _parse_block(
            lines, index + 1, end, base_indent
        )
        local_types: dict[str, TypeRef] = {parameter.name: parameter.ty for parameter in params}
        if len(local_types) != len(params):
            raise GlyphError(f"{line}行目: 関数引数名が重複")
        seen = set(local_types)
        resolved: list[tuple[_RawBinding, TypeRef, str, str]] = []
        lambda_definitions: list[str] = []

        for binding_index, binding in enumerate(raw_bindings):
            if binding.name in seen:
                raise GlyphError(f"{binding.line}行目: 中間値 '{binding.name}' は既に定義済み")
            if binding.kind == "conditional":
                type_ref = _infer_guard_result(
                    binding.guards,
                    local_types,
                    signatures,
                    products,
                    variants,
                    variant_defs,
                    global_names,
                    token_macros,
                    ast_macros,
                )
                lowered_source = binding.source
            else:
                lowered_source, type_ref, lambdas, definitions = _lower_pipeline(
                    binding.source,
                    binding.line,
                    local_types,
                    None,
                    signatures,
                    products,
                    variants,
                    global_names,
                    impure,
                    token_macros,
                    ast_macros,
                    lambda_counter,
                )
                block_lambdas.extend(lambdas)
                lambda_definitions.extend(definitions)

            value_helper = f"__glyph_block_L{line}_{binding_index}_value"
            available = tuple(
                Param(local_name, local_type) for local_name, local_type in local_types.items()
            )
            if binding.kind == "conditional":
                generated.append(
                    f">{value_helper}({_render_params(available)}):{_render_type(type_ref)}"
                )
                generated.extend(
                    "  " + ("_" if condition is None else condition) + " => " + value
                    for condition, value, _ in binding.guards
                )
            else:
                generated.append(
                    f">{value_helper}({_render_params(available)}):"
                    f"{_render_type(type_ref)}={lowered_source}"
                )
            resolved.append((binding, type_ref, lowered_source, value_helper))
            local_types[binding.name] = type_ref
            seen.add(binding.name)

        lowered_final, final_type, lambdas, definitions = _lower_pipeline(
            final_source,
            final_line,
            local_types,
            return_type,
            signatures,
            products,
            variants,
            global_names,
            impure,
            token_macros,
            ast_macros,
            lambda_counter,
        )
        block_lambdas.extend(lambdas)
        lambda_definitions.extend(definitions)
        if final_type != return_type:
            raise GlyphError(
                f"{final_line}行目: 関数 '{name}' は{_render_type(return_type)}を返す必要があるが"
                f"{_render_type(final_type)}を返す"
            )

        final_helper = f"__glyph_block_L{line}_final"
        all_params = tuple(
            Param(local_name, local_type) for local_name, local_type in local_types.items()
        )
        generated.append(
            f">{final_helper}({_render_params(all_params)}):"
            f"{_render_type(return_type)}={lowered_final}"
        )

        continuations = tuple(
            f"__glyph_block_L{line}_{binding_index}_next"
            for binding_index in range(len(resolved))
        )
        original_args = [parameter.name for parameter in params]
        first_binding, _, first_source, first_helper = resolved[0]
        first_value = (
            _render_call(first_helper, original_args)
            if first_binding.kind == "conditional"
            else first_source
        )
        main_body = _render_call(continuations[0], [*original_args, first_value])
        output[index] = stripped + "=" + main_body + ((" " + comment) if comment else "")
        for consumed_index in consumed:
            output[consumed_index] = ""

        available_names = list(original_args)
        available_params = list(params)
        for binding_index, (binding, type_ref, lowered_source, _) in enumerate(resolved):
            available_names.append(binding.name)
            available_params.append(Param(binding.name, type_ref))
            if binding_index + 1 < len(resolved):
                next_binding, _, next_source, next_helper = resolved[binding_index + 1]
                next_value = (
                    _render_call(next_helper, available_names)
                    if next_binding.kind == "conditional"
                    else next_source
                )
                body = _render_call(
                    continuations[binding_index + 1], [*available_names, next_value]
                )
            else:
                body = lowered_final
            generated.append(
                f">{continuations[binding_index]}({_render_params(available_params)}):"
                f"{_render_type(return_type)}={body}"
            )

        blocks.append(
            FunctionBlockLowering(
                name,
                line,
                tuple(
                    BlockBindingLowering(
                        raw.name, type_ref, raw.line, raw.kind, raw.source, helper
                    )
                    for raw, type_ref, _, helper in resolved
                ),
                final_source,
                final_line,
                final_helper,
                continuations,
            )
        )
        generated.extend(lambda_definitions)
        index = end

    if generated:
        output.extend(["", "# generated immutable function blocks", *generated])

    return FunctionBlockLoweringResult(
        "\n".join(output) + ("\n" if source.endswith("\n") else ""),
        tuple(blocks),
        tuple(block_lambdas),
    )


def restore_block_source_lines(
    program: Program, blocks: Sequence[FunctionBlockLowering]
) -> Program:
    line_by_name: dict[str, int] = {}
    for block in blocks:
        line_by_name[block.final_helper] = block.final_line
        for binding in block.bindings:
            line_by_name[binding.value_helper] = binding.line
        for helper, binding in zip(block.continuation_helpers, block.bindings):
            line_by_name[helper] = binding.line
    if not line_by_name:
        return program
    declarations = []
    for declaration in program.declarations:
        if isinstance(declaration, FunctionDecl) and declaration.name in line_by_name:
            declarations.append(replace(declaration, line=line_by_name[declaration.name]))
        else:
            declarations.append(declaration)
    return Program(tuple(declarations))

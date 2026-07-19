from __future__ import annotations

import re
from pathlib import Path

from .compiler import (
    GlyphError,
    Program,
    RustGenerator,
    _find_matching,
    _find_top_level_char,
    _split_top_level,
    parse_program as _parse_program,
)


# 型位置だけで有効な、制御・組み込み用途向けの既定幅。
_TYPE_SHORTCUTS = {
    "f": "f32",
    "d": "f64",
    "u": "u16",
    "i": "i32",
    "b": "bool",
}


def _declared_type_names(lines: list[str]) -> set[str]:
    names: set[str] = set()
    for original in lines:
        clean = original.split("#", 1)[0].strip()
        if not clean or clean[0] not in "*+=":
            continue
        if clean.startswith("*"):
            match = re.match(r"\*\s*([A-Za-z_]\w*)\s*\(", clean)
        elif clean.startswith("+"):
            match = re.match(r"\+\s*([A-Za-z_]\w*)\s*=", clean)
        else:
            match = re.match(r"=\s*([A-Za-z_]\w*)\s*=", clean)
        if match:
            names.add(match.group(1))
    return names


def _expand_type(text: str, declared_types: set[str]) -> str:
    text = text.strip()
    pipe = _find_top_level_char(text, "|")
    if pipe >= 0:
        success = text[:pipe].strip()
        error = text[pipe + 1 :].strip()
        if not success or not error:
            raise GlyphError(f"結果型は T|E の形式で記述する: {text}")
        return f"R<{_expand_type(success, declared_types)},{_expand_type(error, declared_types)}>"

    if text.startswith("("):
        close = _find_matching(text, 0)
        if close == len(text) - 1:
            inner = text[1:-1]
            return "(" + ",".join(
                _expand_type(part, declared_types)
                for part in _split_top_level(inner, ",")
                if part
            ) + ")"

    angle = text.find("<")
    if angle > 0:
        close = _find_matching(text, angle, "<", ">")
        if close == len(text) - 1:
            name = text[:angle].strip()
            args = _split_top_level(text[angle + 1 : close], ",")
            expanded_name = (
                name
                if name in declared_types
                else _TYPE_SHORTCUTS.get(name, name)
            )
            return (
                f"{expanded_name}<"
                f"{','.join(_expand_type(arg, declared_types) for arg in args)}>"
            )

    if text in declared_types:
        return text
    return _TYPE_SHORTCUTS.get(text, text)


def _expand_fields(
    text: str,
    declared_types: set[str],
    products: dict[str, tuple[str, ...]],
    *,
    allow_spread: bool,
) -> tuple[str, ...]:
    if not text.strip():
        return ()

    output: list[str] = []
    pending: list[str] = []
    for part in _split_top_level(text, ","):
        stripped = part.strip()
        if allow_spread and stripped.startswith("*") and stripped[1:].isidentifier():
            if pending:
                raise GlyphError("型省略中の名前列の後ろでは *Product を展開できない")
            product_name = stripped[1:]
            if product_name not in products:
                raise GlyphError(f"展開する積型 '*{product_name}' が定義されていない")
            output.extend(products[product_name])
            continue

        colon = _find_top_level_char(stripped, ":")
        if colon < 0:
            pending.append(stripped)
            continue

        name = stripped[:colon].strip()
        ty = _expand_type(stripped[colon + 1 :], declared_types)
        names = [*pending, name]
        pending.clear()
        output.extend(f"{item}:{ty}" for item in names)

    # 不完全な name,name は既存パーサーへ残し、従来どおりの構文エラーにする。
    if pending:
        output.extend(pending)
    return tuple(output)


def _replace_parenthesized_fields(
    code: str,
    declared_types: set[str],
    products: dict[str, tuple[str, ...]],
    *,
    allow_spread: bool,
) -> str:
    open_pos = code.find("(")
    if open_pos < 0:
        return code
    close_pos = _find_matching(code, open_pos)
    fields = _expand_fields(
        code[open_pos + 1 : close_pos],
        declared_types,
        products,
        allow_spread=allow_spread,
    )
    return code[: open_pos + 1] + ",".join(fields) + code[close_pos:]


def _expand_signature(
    code: str,
    declared_types: set[str],
    products: dict[str, tuple[str, ...]],
) -> str:
    code = _replace_parenthesized_fields(
        code, declared_types, products, allow_spread=True
    )
    open_pos = code.find("(")
    if open_pos < 0:
        return code
    close_pos = _find_matching(code, open_pos)
    rest = code[close_pos + 1 :]
    colon = rest.find(":")
    if colon < 0:
        return code

    before_type = code[: close_pos + 1] + rest[: colon + 1]
    typed_body = rest[colon + 1 :]
    eq = _find_top_level_char(typed_body, "=")
    if eq >= 0:
        return_type = _expand_type(typed_body[:eq], declared_types)
        return before_type + return_type + typed_body[eq:]
    return before_type + _expand_type(typed_body, declared_types)


def _expand_sum(code: str, declared_types: set[str]) -> str:
    eq = _find_top_level_char(code[1:], "=")
    if eq < 0:
        return code
    eq += 1
    prefix = code[: eq + 1]
    variants_text = code[eq + 1 :]
    variants: list[str] = []
    for item in _split_top_level(variants_text, "|"):
        if "(" in item:
            open_pos = item.find("(")
            close_pos = _find_matching(item, open_pos)
            args = _split_top_level(item[open_pos + 1 : close_pos], ",")
            item = (
                item[: open_pos + 1]
                + ",".join(
                    _expand_type(arg, declared_types) for arg in args if arg
                )
                + item[close_pos:]
            )
        elif "{" in item:
            open_pos = item.find("{")
            close_pos = _find_matching(item, open_pos, "{", "}")
            fields = _expand_fields(
                item[open_pos + 1 : close_pos],
                declared_types,
                {},
                allow_spread=False,
            )
            item = item[: open_pos + 1] + ",".join(fields) + item[close_pos:]
        variants.append(item)
    return prefix + "|".join(variants)


def _expand_alias(code: str, declared_types: set[str]) -> str:
    eq = _find_top_level_char(code[1:], "=")
    if eq < 0:
        return code
    eq += 1
    return code[: eq + 1] + _expand_type(code[eq + 1 :], declared_types)


def _split_comment(line: str) -> tuple[str, str]:
    index = line.find("#")
    if index < 0:
        return line, ""
    return line[:index].rstrip(), line[index:]


def expand_compact_syntax(source: str) -> str:
    """短縮文法を、行数を変えずに従来Glyph文法へ展開する。"""
    raw_lines = source.splitlines()
    declared_types = _declared_type_names(raw_lines)
    products: dict[str, tuple[str, ...]] = {}

    # 積型のfield rowを先に集め、後方参照の `*Product` も展開可能にする。
    for original in raw_lines:
        code, _ = _split_comment(original)
        stripped = code.strip()
        if not stripped.startswith("*"):
            continue
        open_pos = stripped.find("(")
        if open_pos <= 1:
            continue
        close_pos = _find_matching(stripped, open_pos)
        name = stripped[1:open_pos].strip()
        products[name] = _expand_fields(
            stripped[open_pos + 1 : close_pos],
            declared_types,
            products,
            allow_spread=False,
        )

    transformed: list[str] = []
    for original in raw_lines:
        code, comment = _split_comment(original)
        if not code.strip():
            transformed.append(original)
            continue

        indent = code[: len(code) - len(code.lstrip())]
        stripped = code.strip()
        if not indent:
            marker = stripped[0]
            if marker == "*":
                stripped = _replace_parenthesized_fields(
                    stripped, declared_types, products, allow_spread=False
                )
            elif marker in ">!":
                stripped = _expand_signature(stripped, declared_types, products)
            elif marker == "+":
                stripped = _expand_sum(stripped, declared_types)
            elif marker == "=":
                stripped = _expand_alias(stripped, declared_types)
            code = stripped
        elif ">>" in stripped:
            # ガード行だけで短い `>>` を既存文法の `=>` へ展開する。
            code = indent + stripped.replace(">>", "=>", 1)

        if comment:
            transformed.append(code + (" " if code else "") + comment)
        else:
            transformed.append(code)

    return "\n".join(transformed) + ("\n" if source.endswith("\n") else "")


def parse_program(source: str) -> Program:
    return _parse_program(expand_compact_syntax(source))


def compile_source(source: str) -> str:
    return RustGenerator(parse_program(source)).generate()


def compile_file(input_path: str | Path, output_path: str | Path) -> None:
    source = Path(input_path).read_text(encoding="utf-8")
    generated = compile_source(source)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(generated, encoding="utf-8")

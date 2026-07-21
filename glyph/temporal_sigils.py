from __future__ import annotations

import re

from .compiler import GlyphError


_RESERVED_TEMPORAL_NAMES = {"A", "E"}
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def reject_reserved_temporal_macro_names(source: str) -> None:
    """Reserve A and E so `@A` / `@E` are unambiguously temporal operators."""

    for line_no, original in enumerate(source.splitlines(), start=1):
        code = original.split("#", 1)[0]
        if code[:1].isspace():
            continue
        stripped = code.strip()
        if not stripped.startswith("@") or stripped == "@end":
            continue
        match = _IDENTIFIER_RE.match(stripped, 1)
        if match is None:
            continue
        name = match.group(0)
        if name in _RESERVED_TEMPORAL_NAMES:
            raise GlyphError(
                f"{line_no}行目: '{name}' は時相演算子 '@{name}' のため予約済み"
            )


def _formula_equal(code: str) -> int:
    depth = 0
    for index, char in enumerate(code):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "=" and depth == 0:
            return index
    return -1


def _normalize_formula(formula: str, line_no: int) -> str:
    if "□" in formula or "◇" in formula:
        raise GlyphError(
            f"{line_no}行目: 時相演算子には '@A' と '@E' を使う"
        )

    output: list[str] = []
    index = 0
    while index < len(formula):
        char = formula[index]
        if char == "@":
            if index + 1 >= len(formula) or formula[index + 1] not in "AE":
                raise GlyphError(
                    f"{line_no}行目: 時相式の '@' の後には 'A' または 'E' が必要"
                )
            operator = formula[index + 1]
            after = index + 2
            if after < len(formula) and (
                formula[after].isalnum() or formula[after] == "_"
            ):
                raise GlyphError(
                    f"{line_no}行目: '@{operator}' の後に空白、括弧、"
                    "または別の '@A'/'@E' を置く"
                )
            output.append(operator)
            index += 2
            continue

        if char.isalpha() or char == "_":
            match = _IDENTIFIER_RE.match(formula, index)
            assert match is not None
            word = match.group(0)
            if set(word) <= _RESERVED_TEMPORAL_NAMES:
                rendered = "".join(f"@{item}" for item in word)
                raise GlyphError(
                    f"{line_no}行目: 裸の時相演算子 '{word}' は使用できない。"
                    f"'{rendered}' を使う"
                )
            output.append(word)
            index = match.end()
            continue

        output.append(char)
        index += 1

    return "".join(output)


def normalize_temporal_sigils(source: str) -> str:
    """Translate source-level `@A` / `@E` into the compact parser's internal form.

    Only top-level temporal declarations are touched. Line count and all non-temporal
    source text remain unchanged so the existing source-map pipeline stays valid.
    """

    transformed: list[str] = []
    for line_no, original in enumerate(source.splitlines(), start=1):
        code, marker, comment = original.partition("#")
        stripped = code.strip()
        if code[:1].isspace() or not stripped.startswith("?"):
            transformed.append(original)
            continue

        equal = _formula_equal(code)
        if equal < 0:
            transformed.append(original)
            continue
        normalized = _normalize_formula(code[equal + 1 :], line_no)
        rebuilt = code[: equal + 1] + normalized
        if marker:
            rebuilt += marker + comment
        transformed.append(rebuilt)

    suffix = "\n" if source.endswith("\n") else ""
    return "\n".join(transformed) + suffix

from __future__ import annotations

from dataclasses import dataclass

from .compiler import GlyphError


@dataclass(frozen=True)
class LayoutNormalization:
    source: str
    changed: bool


def _code(line: str) -> str:
    return line.split("#", 1)[0].rstrip()


def _depths(text: str) -> tuple[int, int, int]:
    round_depth = square_depth = brace_depth = 0
    for char in text:
        if char == "(":
            round_depth += 1
        elif char == ")":
            round_depth -= 1
        elif char == "[":
            square_depth += 1
        elif char == "]":
            square_depth -= 1
        elif char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
        if min(round_depth, square_depth, brace_depth) < 0:
            raise GlyphError("宣言の閉じ括弧が開始括弧より前にある")
    return round_depth, square_depth, brace_depth


def _open(depths: tuple[int, int, int]) -> bool:
    return any(value > 0 for value in depths)


def _declaration_start(stripped: str) -> bool:
    return stripped.startswith(("*", "+", "=", ">", "!", "~", "resource "))


def normalize_multiline_declarations(source: str) -> LayoutNormalization:
    """Join balanced top-level declaration headers without changing line count.

    Existing one-line source is returned byte-for-byte. Continuation lines are replaced by
    blank lines so all downstream diagnostics and source maps retain their original indices.
    """

    lines = source.splitlines()
    output = list(lines)
    changed = False
    index = 0

    while index < len(lines):
        original = lines[index]
        code = _code(original)
        stripped = code.strip()
        if not stripped or code[:1].isspace() or not _declaration_start(stripped):
            index += 1
            continue

        depths = _depths(code)
        if not _open(depths):
            index += 1
            continue

        parts = [stripped]
        cursor = index + 1
        while cursor < len(lines) and _open(depths):
            next_code = _code(lines[cursor])
            if next_code.strip():
                parts.append(next_code.strip())
                current = " ".join(parts)
                depths = _depths(current)
            output[cursor] = ""
            cursor += 1

        if _open(depths):
            raise GlyphError(f"{index + 1}行目: 複数行宣言の括弧が閉じられていない")

        comment = ""
        if "#" in original:
            comment = " " + original[original.index("#") :]
        output[index] = " ".join(parts) + comment
        changed = True
        index = cursor

    suffix = "\n" if source.endswith("\n") else ""
    return LayoutNormalization("\n".join(output) + suffix, changed)

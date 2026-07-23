from __future__ import annotations

import re

from .compiler import _find_top_level_char


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_PATH = rf"{_IDENT}(?:\.{_IDENT})*"
_RESOLVE = re.compile(rf"\(\s*&\s*(?P<name>{_PATH})\s+as\s+share\s*\)\s*\?")
_BORROW_CAST = re.compile(rf"&\s*(?P<name>{_PATH})\s+as\s+(?:share|link)\b")
_PUBLISH = re.compile(rf"\b(?P<name>{_PATH})\s+as\s+share\b")
_MUT_BORROW = re.compile(rf"&\s*mut\s+(?P<name>{_PATH})\b")
_READ_BORROW = re.compile(rf"&\s*(?P<name>{_PATH})\b")


def lower_capability_expression(text: str) -> str:
    """Lower static Capability operations into compatibility Rust expressions.

    The Rust backend still uses the legacy object representation. Clone-based lowering keeps
    affine source variables usable while `verification-report.json` records that real
    Arc/Weak/link liveness behavior is a Host adapter obligation.
    """

    output = _RESOLVE.sub(lambda match: f"{match.group('name')}.clone()", text)
    output = _BORROW_CAST.sub(lambda match: f"{match.group('name')}.clone()", output)
    output = _PUBLISH.sub(lambda match: match.group("name"), output)
    output = _MUT_BORROW.sub(lambda match: f"{match.group('name')}.clone()", output)
    output = _READ_BORROW.sub(lambda match: f"{match.group('name')}.clone()", output)
    return output


def lower_capability_codegen(original_source: str, erased_source: str) -> str:
    original = original_source.splitlines()
    rendered = erased_source.splitlines()
    for index, original_line in enumerate(original):
        if index >= len(rendered):
            break
        code, marker, comment = original_line.partition("#")
        stripped = code.strip()
        if not stripped or not any(token in stripped for token in (" as ", "&mut ", "&")):
            continue
        indent = code[: len(code) - len(code.lstrip())]
        if not code[:1].isspace() and stripped.startswith((">", "!", "~")):
            original_equal = _find_top_level_char(stripped, "=")
            rendered_equal = _find_top_level_char(rendered[index], "=")
            if original_equal >= 0 and rendered_equal >= 0:
                rendered[index] = (
                    rendered[index][: rendered_equal + 1]
                    + lower_capability_expression(stripped[original_equal + 1 :])
                )
        elif code[:1].isspace():
            rendered[index] = indent + lower_capability_expression(stripped)
        if marker:
            rendered[index] += " #" + comment
    output = "\n".join(rendered)
    if original_source.endswith("\n"):
        output += "\n"
    return output

from __future__ import annotations

import re

from .compiler import GlyphError, _find_matching, _find_top_level_char, _split_top_level


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_SIGNATURE_RE = re.compile(rf"^[>!~]\s*(?P<name>{_IDENT})\s*\(")
_AS_ANY_RE = re.compile(
    rf"(?P<borrow>&\s*)?(?P<source>{_IDENT}(?:\.{_IDENT})*)"
    rf"\s+as\s+(?P<target>{_IDENT})"
)
_MUT_BORROW_RE = re.compile(rf"&\s*mut\s+(?P<name>{_IDENT})\b")


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].rstrip()


def _parameter_capabilities(signature: str, line: int) -> dict[str, str]:
    open_pos = signature.find("(")
    if open_pos < 0:
        return {}
    close_pos = _find_matching(signature, open_pos)
    capabilities: dict[str, str] = {}
    pending: list[str] = []
    for item in _split_top_level(signature[open_pos + 1 : close_pos], ","):
        part = item.strip()
        colon = _find_top_level_char(part, ":")
        if colon < 0:
            pending.append(part)
            continue
        name = part[:colon].strip()
        type_text = part[colon + 1 :].strip()
        names = [*pending, name]
        pending.clear()
        capability = "plain"
        for candidate in ("own", "share", "link"):
            if type_text.startswith(candidate + " "):
                capability = candidate
                break
        elif type_text.startswith("&mut "):
            capability = "borrow_mut"
        elif type_text.startswith("&"):
            capability = "borrow"
        for parameter in names:
            if re.fullmatch(_IDENT, parameter):
                capabilities[parameter] = capability
    return capabilities


def validate_capability_surface(source: str) -> None:
    """Reject capability misuse before legacy expression/block parsing.

    The capability layer erases valid capability syntax before the old parser runs. Invalid
    capability syntax must therefore be diagnosed here rather than leaking an unrelated
    legacy-parser error.
    """

    lines = source.splitlines()
    current_params: dict[str, str] = {}

    for line_no, original in enumerate(lines, start=1):
        code = _strip_comment(original)
        stripped = code.strip()
        if not stripped:
            continue

        if not code[:1].isspace():
            current_params = {}
            if _SIGNATURE_RE.match(stripped):
                current_params = _parameter_capabilities(stripped, line_no)

        for match in _AS_ANY_RE.finditer(stripped):
            source_name = match.group("source").split(".", 1)[0]
            source_capability = current_params.get(source_name)
            target = match.group("target")
            borrowed = match.group("borrow") is not None
            allowed = (
                target in {"share", "link"}
                and (
                    (
                        not borrowed
                        and source_capability == "own"
                        and target == "share"
                    )
                    or (
                        borrowed
                        and source_capability == "share"
                        and target in {"share", "link"}
                    )
                    or (
                        borrowed
                        and source_capability == "link"
                        and target in {"share", "link"}
                    )
                )
            )
            if not allowed:
                rendered_source = source_capability or "unknown"
                raise GlyphError(
                    f"{line_no}行目: {rendered_source} から"
                    f" {'&' if borrowed else ''}as {target} へ変換できない"
                )

        for match in _MUT_BORROW_RE.finditer(stripped):
            name = match.group("name")
            capability = current_params.get(name)
            if capability in {"share", "link"}:
                raise GlyphError(
                    f"{line_no}行目: {capability}値 '{name}' から &mut を取得できない"
                )

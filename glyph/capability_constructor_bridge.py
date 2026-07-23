from __future__ import annotations

from dataclasses import dataclass
import re

from .capabilities import CapabilityExtraction, CapabilityModel, extract_capabilities
from .compiler import GlyphError, _find_matching, _find_top_level_char, _split_top_level


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_CAPABILITY_TOKEN = re.compile(r"(?:^|[:,(])\s*(?:own|share|link|&mut|&)(?:\s|[A-Za-z_])")


@dataclass(frozen=True)
class _Synthetic:
    line: str
    name: str


def _product_signature(stripped: str) -> _Synthetic | None:
    open_pos = stripped.find("(")
    if open_pos <= 1:
        return None
    close_pos = _find_matching(stripped, open_pos)
    if close_pos != len(stripped) - 1:
        return None
    name = stripped[1:open_pos].strip()
    fields = stripped[open_pos + 1 : close_pos].strip()
    if not re.fullmatch(_IDENT, name) or not _CAPABILITY_TOKEN.search(fields):
        return None
    return _Synthetic(f">{name}({fields}):{name}", name)


def _sum_signatures(stripped: str) -> tuple[_Synthetic, ...]:
    equal = _find_top_level_char(stripped[1:], "=")
    if equal < 0:
        return ()
    equal += 1
    sum_name = stripped[1:equal].strip()
    output: list[_Synthetic] = []
    for variant in _split_top_level(stripped[equal + 1 :], "|"):
        item = variant.strip()
        open_pos = item.find("(")
        if open_pos <= 0:
            continue
        close_pos = _find_matching(item, open_pos)
        variant_name = item[:open_pos].strip()
        args = [part.strip() for part in _split_top_level(item[open_pos + 1 : close_pos], ",") if part.strip()]
        if not args or not any(_CAPABILITY_TOKEN.search(":" + arg) for arg in args):
            continue
        params = ",".join(f"arg{index}:{arg}" for index, arg in enumerate(args))
        output.append(_Synthetic(f">{variant_name}({params}):{sum_name}", variant_name))
    return tuple(output)


def _synthetics(source: str) -> tuple[_Synthetic, ...]:
    output: list[_Synthetic] = []
    for original in source.splitlines():
        code = original.split("#", 1)[0].strip()
        if code.startswith("*"):
            item = _product_signature(code)
            if item is not None:
                output.append(item)
        elif code.startswith("+"):
            output.extend(_sum_signatures(code))
    return tuple(output)


def extract_capabilities_with_constructors(source: str) -> CapabilityExtraction:
    constructors = _synthetics(source)
    if not constructors:
        return extract_capabilities(source)

    original_lines = len(source.splitlines())
    suffix = "" if source.endswith("\n") else "\n"
    augmented = source + suffix + "\n".join(item.line for item in constructors) + "\n"
    extracted = extract_capabilities(augmented)

    rendered_lines = extracted.source.splitlines()
    rendered = "\n".join(rendered_lines[:original_lines])
    if source.endswith("\n"):
        rendered += "\n"

    constructor_names = {item.name for item in constructors}
    functions = tuple(
        function
        for function in extracted.model.functions
        if not (function.line > original_lines and function.name in constructor_names)
    )
    model = CapabilityModel(
        extracted.model.resources,
        functions,
        extracted.model.aggregates,
        extracted.model.operations,
    )
    return CapabilityExtraction(rendered, model)

from __future__ import annotations

from dataclasses import dataclass
import re

from .capabilities import (
    CapabilityExtraction,
    CapabilityModel,
    _erase_expression,
    extract_capabilities,
)
from .compiler import GlyphError, _find_matching, _find_top_level_char, _split_top_level


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_CAPABILITY_TOKEN = re.compile(
    r"(?:^|[:,(])\s*(?:own|share|link|&mut|&)(?:\s|[A-Za-z_])"
)
_CALL_HEAD = re.compile(rf"(?P<name>{_IDENT})\s*\(")


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
        args = [
            part.strip()
            for part in _split_top_level(item[open_pos + 1 : close_pos], ",")
            if part.strip()
        ]
        if not args or not any(
            _CAPABILITY_TOKEN.search(":" + arg) for arg in args
        ):
            continue
        params = ",".join(
            f"arg{index}:{arg}" for index, arg in enumerate(args)
        )
        output.append(
            _Synthetic(f">{variant_name}({params}):{sum_name}", variant_name)
        )
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


def _call(text: str) -> tuple[str, tuple[str, ...]] | None:
    value = text.strip()
    suffix = "?" if value.endswith("?") else ""
    if suffix:
        value = value[:-1].rstrip()
    match = _CALL_HEAD.match(value)
    if match is None:
        return None
    open_pos = value.find("(", match.start())
    close_pos = _find_matching(value, open_pos)
    if close_pos != len(value) - 1:
        return None
    arguments = tuple(
        item.strip()
        for item in _split_top_level(value[open_pos + 1 : close_pos], ",")
        if item.strip()
    )
    return match.group("name"), arguments


def _unwrap_to_capability_constructor(
    expression: str,
    constructor_names: set[str],
) -> str:
    """Remove transparent Result wrappers only in the capability analysis copy."""

    parsed = _call(expression)
    if parsed is None:
        return expression
    name, arguments = parsed
    if name in constructor_names:
        return expression.strip()
    if len(arguments) != 1:
        return expression
    nested = _unwrap_to_capability_constructor(arguments[0], constructor_names)
    if nested != arguments[0] or _call(nested) is not None:
        nested_call = _call(nested)
        if nested_call is not None and nested_call[0] in constructor_names:
            return nested
    return expression


def _analysis_source(
    source: str,
    constructor_names: set[str],
) -> tuple[str, set[int]]:
    lines = source.splitlines()
    output = list(lines)
    changed: set[int] = set()

    for index, original in enumerate(lines):
        code, marker, comment = original.partition("#")
        stripped = code.strip()
        if not stripped:
            continue
        replacement = stripped
        if not code[:1].isspace() and stripped.startswith((">", "!", "~")):
            equal = _find_top_level_char(stripped, "=")
            if equal >= 0:
                expression = stripped[equal + 1 :]
                unwrapped = _unwrap_to_capability_constructor(
                    expression,
                    constructor_names,
                )
                if unwrapped != expression:
                    replacement = stripped[: equal + 1] + unwrapped
        elif code[:1].isspace():
            if ">>" in stripped:
                prefix, expression = stripped.split(">>", 1)
                unwrapped = _unwrap_to_capability_constructor(
                    expression,
                    constructor_names,
                )
                if unwrapped != expression:
                    replacement = prefix + ">>" + unwrapped
            else:
                binding = stripped.find(":=")
                if binding >= 0:
                    expression = stripped[binding + 2 :]
                    unwrapped = _unwrap_to_capability_constructor(
                        expression,
                        constructor_names,
                    )
                    if unwrapped != expression:
                        replacement = stripped[: binding + 2] + unwrapped
                else:
                    replacement = _unwrap_to_capability_constructor(
                        stripped,
                        constructor_names,
                    )

        if replacement != stripped:
            indent = code[: len(code) - len(code.lstrip())]
            output[index] = indent + replacement
            if marker:
                output[index] += " #" + comment
            changed.add(index)

    suffix = "\n" if source.endswith("\n") else ""
    return "\n".join(output) + suffix, changed


def _restore_generation_source(
    source: str,
    extracted_source: str,
    changed_lines: set[int],
) -> str:
    original = source.splitlines()
    rendered = extracted_source.splitlines()
    for index in changed_lines:
        if index >= len(original) or index >= len(rendered):
            continue
        code, marker, comment = original[index].partition("#")
        stripped = code.strip()
        indent = code[: len(code) - len(code.lstrip())]
        if not code[:1].isspace() and stripped.startswith((">", "!", "~")):
            original_equal = _find_top_level_char(stripped, "=")
            rendered_equal = _find_top_level_char(rendered[index], "=")
            if original_equal >= 0 and rendered_equal >= 0:
                rendered[index] = (
                    rendered[index][: rendered_equal + 1]
                    + _erase_expression(stripped[original_equal + 1 :])
                )
        elif code[:1].isspace():
            rendered[index] = indent + _erase_expression(stripped)
        if marker:
            rendered[index] += " #" + comment
    output = "\n".join(rendered[: len(original)])
    if source.endswith("\n"):
        output += "\n"
    return output


def extract_capabilities_with_constructors(source: str) -> CapabilityExtraction:
    constructors = _synthetics(source)
    if not constructors:
        return extract_capabilities(source)

    constructor_names = {item.name for item in constructors}
    analysis_source, changed_lines = _analysis_source(source, constructor_names)
    original_lines = len(source.splitlines())
    suffix = "" if analysis_source.endswith("\n") else "\n"
    augmented = (
        analysis_source
        + suffix
        + "\n".join(item.line for item in constructors)
        + "\n"
    )
    extracted = extract_capabilities(augmented)
    rendered = _restore_generation_source(
        source,
        extracted.source,
        changed_lines,
    )

    functions = tuple(
        function
        for function in extracted.model.functions
        if not (
            function.line > original_lines
            and function.name in constructor_names
        )
    )
    model = CapabilityModel(
        extracted.model.resources,
        functions,
        extracted.model.aggregates,
        tuple(
            operation
            for operation in extracted.model.operations
            if operation.function not in constructor_names
        ),
    )
    return CapabilityExtraction(rendered, model)

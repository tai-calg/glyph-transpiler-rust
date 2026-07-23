from __future__ import annotations

from dataclasses import dataclass
import re

from .capabilities import (
    CapabilityExtraction,
    CapabilityFunction,
    CapabilityModel,
    CapabilityOperation,
    CapabilityParam,
    CapabilityType,
    parse_capability_type,
)
from .capability_constructor_bridge import extract_capabilities_with_constructors
from .compiler import _find_matching, _find_top_level_char, _split_top_level


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_PREFIX = "__glyph_place_"


@dataclass(frozen=True)
class _Field:
    name: str
    type: CapabilityType


@dataclass(frozen=True)
class _ExpandedParam:
    function: str
    parameter: str
    original_type: CapabilityType
    fields: tuple[tuple[str, str], ...]


def _products(source: str) -> dict[str, tuple[_Field, ...]]:
    output: dict[str, tuple[_Field, ...]] = {}
    for original in source.splitlines():
        code = original.split("#", 1)[0].strip()
        if not code.startswith("*"):
            continue
        open_pos = code.find("(")
        if open_pos <= 1:
            continue
        close_pos = _find_matching(code, open_pos)
        if close_pos != len(code) - 1:
            continue
        name = code[1:open_pos].strip()
        if not re.fullmatch(_IDENT, name):
            continue
        fields: list[_Field] = []
        pending: list[str] = []
        for part in _split_top_level(code[open_pos + 1 : close_pos], ","):
            item = part.strip()
            colon = _find_top_level_char(item, ":")
            if colon < 0:
                pending.append(item)
                continue
            field_name = item[:colon].strip()
            field_type = parse_capability_type(item[colon + 1 :])
            names = [*pending, field_name]
            pending.clear()
            for candidate in names:
                if field_type.capability.value != "plain":
                    fields.append(_Field(candidate, field_type))
        if fields:
            output[name] = tuple(fields)
    return output


def _transform_header(
    stripped: str,
    products: dict[str, tuple[_Field, ...]],
    line: int,
) -> tuple[str, tuple[_ExpandedParam, ...]]:
    marker = stripped[0]
    if marker not in ">!~":
        return stripped, ()
    open_pos = stripped.find("(")
    if open_pos <= 1:
        return stripped, ()
    close_pos = _find_matching(stripped, open_pos)
    name = stripped[1:open_pos].strip()
    params: list[str] = []
    expanded: list[_ExpandedParam] = []
    additions: list[str] = []
    for part in _split_top_level(stripped[open_pos + 1 : close_pos], ","):
        item = part.strip()
        colon = _find_top_level_char(item, ":")
        if colon < 0:
            params.append(item)
            continue
        param_name = item[:colon].strip()
        ty = parse_capability_type(item[colon + 1 :])
        fields = products.get(ty.name)
        if ty.capability.value != "own" or fields is None:
            params.append(item)
            continue
        params.append(f"{param_name}:{ty.name}")
        mapping: list[tuple[str, str]] = []
        for field in fields:
            synthetic = f"{_PREFIX}{param_name}_{field.name}"
            additions.append(f"{synthetic}:{field.type.raw}")
            mapping.append((synthetic, f"{param_name}.{field.name}"))
        expanded.append(_ExpandedParam(name, param_name, ty, tuple(mapping)))
    params.extend(additions)
    return (
        stripped[: open_pos + 1]
        + ",".join(params)
        + stripped[close_pos:],
        tuple(expanded),
    )


def _replace_paths(text: str, expansions: tuple[_ExpandedParam, ...], reverse: bool) -> str:
    output = text
    pairs = [pair for expansion in expansions for pair in expansion.fields]
    for synthetic, place in pairs:
        source, target = (synthetic, place) if reverse else (place, synthetic)
        output = re.sub(rf"\b{re.escape(source)}\b", target, output)
    return output


def _expand_source(source: str) -> tuple[str, tuple[_ExpandedParam, ...]]:
    products = _products(source)
    if not products:
        return source, ()
    lines = source.splitlines()
    output = list(lines)
    expansions: list[_ExpandedParam] = []
    current: tuple[_ExpandedParam, ...] = ()
    for index, original in enumerate(lines):
        code, marker, comment = original.partition("#")
        stripped = code.strip()
        if not stripped:
            continue
        if not code[:1].isspace():
            transformed, current = _transform_header(stripped, products, index + 1)
            expansions.extend(current)
            output[index] = transformed + ((" #" + comment) if marker else "")
            if current:
                output[index] = _replace_paths(output[index], current, reverse=False)
            continue
        if current:
            indent = code[: len(code) - len(code.lstrip())]
            output[index] = indent + _replace_paths(stripped, current, reverse=False)
            if marker:
                output[index] += " #" + comment
    suffix = "\n" if source.endswith("\n") else ""
    return "\n".join(output) + suffix, tuple(expansions)


def _remove_synthetic_params(line: str) -> str:
    stripped = line.strip()
    if not stripped.startswith((">", "!", "~")):
        return line
    open_pos = stripped.find("(")
    if open_pos <= 1:
        return line
    close_pos = _find_matching(stripped, open_pos)
    params = [
        part
        for part in _split_top_level(stripped[open_pos + 1 : close_pos], ",")
        if not part.strip().startswith(_PREFIX)
    ]
    indent = line[: len(line) - len(line.lstrip())]
    return indent + stripped[: open_pos + 1] + ",".join(params) + stripped[close_pos:]


def _restore_source(
    source: str,
    transformed_output: str,
    expansions: tuple[_ExpandedParam, ...],
) -> str:
    lines = transformed_output.splitlines()
    by_function: dict[str, tuple[_ExpandedParam, ...]] = {}
    for expansion in expansions:
        by_function.setdefault(expansion.function, tuple())
        by_function[expansion.function] = (*by_function[expansion.function], expansion)
    current: tuple[_ExpandedParam, ...] = ()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if not line[:1].isspace():
            match = re.match(rf"^[>!~](?P<name>{_IDENT})", stripped)
            current = by_function.get(match.group("name"), ()) if match else ()
            if current:
                lines[index] = _remove_synthetic_params(line)
                lines[index] = _replace_paths(lines[index], current, reverse=True)
        elif current:
            lines[index] = _replace_paths(line, current, reverse=True)
    output = "\n".join(lines[: len(source.splitlines())])
    if source.endswith("\n"):
        output += "\n"
    return output


def _restore_model(
    model: CapabilityModel,
    expansions: tuple[_ExpandedParam, ...],
) -> CapabilityModel:
    by_function: dict[str, tuple[_ExpandedParam, ...]] = {}
    places: dict[tuple[str, str], str] = {}
    for expansion in expansions:
        by_function.setdefault(expansion.function, tuple())
        by_function[expansion.function] = (*by_function[expansion.function], expansion)
        for synthetic, place in expansion.fields:
            places[(expansion.function, synthetic)] = place

    functions: list[CapabilityFunction] = []
    for function in model.functions:
        function_expansions = by_function.get(function.name, ())
        if not function_expansions:
            functions.append(function)
            continue
        original = {item.parameter: item.original_type for item in function_expansions}
        params: list[CapabilityParam] = []
        for param in function.params:
            if param.name.startswith(_PREFIX):
                continue
            params.append(
                CapabilityParam(
                    param.name,
                    original.get(param.name, param.type),
                    param.line,
                )
            )
        functions.append(
            CapabilityFunction(
                function.name,
                function.marker,
                tuple(params),
                function.result,
                function.line,
                function.body_start,
                function.body_end,
            )
        )

    operations = tuple(
        CapabilityOperation(
            operation.function,
            operation.kind,
            places.get((operation.function, operation.source), operation.source),
            places.get((operation.function, operation.target), operation.target),
            operation.capability,
            operation.line,
        )
        for operation in model.operations
    )
    return CapabilityModel(
        model.resources,
        tuple(functions),
        model.aggregates,
        operations,
    )


def extract_capabilities_with_places(source: str) -> CapabilityExtraction:
    transformed, expansions = _expand_source(source)
    if not expansions:
        return extract_capabilities_with_constructors(source)
    extracted = extract_capabilities_with_constructors(transformed)
    return CapabilityExtraction(
        _restore_source(source, extracted.source, expansions),
        _restore_model(extracted.model, expansions),
    )

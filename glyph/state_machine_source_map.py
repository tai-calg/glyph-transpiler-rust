from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from .artifacts import CompilationModel
from .compiler import FunctionDecl


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _generated_guard_line_map(model: CompilationModel) -> dict[int, int]:
    """Map generated function-block guard lines to original Glyph source lines."""

    functions: Mapping[str, FunctionDecl] = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, FunctionDecl)
    }
    source_lines = model.preprocess.source.splitlines()
    mapped: dict[int, int] = {}
    for block in model.expanded.blocks:
        for binding in block.bindings:
            if binding.kind != "conditional" or not (1 <= binding.line <= len(source_lines)):
                continue
            base = source_lines[binding.line - 1].split("#", 1)[0].rstrip()
            base_indent = _indent_width(base)
            source_guard_lines: list[int] = []
            cursor = binding.line
            while cursor < len(source_lines):
                code = source_lines[cursor].split("#", 1)[0].rstrip()
                if not code.strip():
                    cursor += 1
                    continue
                if _indent_width(code) <= base_indent:
                    break
                source_guard_lines.append(model.preprocess.source_line(cursor + 1))
                cursor += 1
            helper = functions.get(binding.value_helper)
            if helper is None:
                continue
            for clause, source_line in zip(helper.guards, source_guard_lines):
                mapped[clause.line] = source_line
    return mapped


def remap_machine_analysis_source_lines(
    model: CompilationModel,
    machine: dict[str, object],
) -> dict[str, object]:
    """Return a copy whose generated helper locations point to user source lines."""

    line_map = _generated_guard_line_map(model)
    if not line_map:
        return machine
    result = deepcopy(machine)
    for transition in result.get("transitions", []):
        source = transition.get("source")
        if isinstance(source, dict) and isinstance(source.get("line"), int):
            source["line"] = line_map.get(source["line"], source["line"])
    branches = result.get("unreachable_branches")
    if isinstance(branches, list):
        result["unreachable_branches"] = [
            line_map.get(line, line) if isinstance(line, int) else line
            for line in branches
        ]
    for diagnostic in result.get("diagnostics", []):
        if (
            isinstance(diagnostic, dict)
            and diagnostic.get("code") == "unreachable-branch"
            and isinstance(diagnostic.get("line"), int)
        ):
            diagnostic["line"] = line_map.get(diagnostic["line"], diagnostic["line"])
    return result

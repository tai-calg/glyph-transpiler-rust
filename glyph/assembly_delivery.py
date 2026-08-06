from __future__ import annotations

import sys
from typing import Callable

from .assembly import extract_assemblies, validate_assemblies


def _patch_function_references(
    original: Callable[..., object],
    replacement: Callable[..., object],
) -> None:
    """Replace already-imported aliases of one public function inside glyph modules."""

    for module_name, module in tuple(sys.modules.items()):
        if module is None or not (module_name == "glyph" or module_name.startswith("glyph.")):
            continue
        namespace = vars(module)
        for name, value in tuple(namespace.items()):
            if value is original:
                namespace[name] = replacement


def install_machine_assembly_delivery() -> None:
    """Install assembly extraction ahead of the canonical compilation parser.

    This is an integration shim for the first implementation slice. It leaves the
    established CompilationModel constructor untouched, preserves all source line
    numbers by blanking assembly blocks, and attaches validated assembly data only
    when the source opts into assembly syntax.
    """

    from . import artifacts as artifacts_module

    current = artifacts_module.parse_compilation_model
    if getattr(current, "__glyph_machine_assembly__", False):
        return
    original = current

    def parse_compilation_model_with_assemblies(
        source: str,
        source_name: str = "input.glyph",
    ):
        parser_source, assemblies = extract_assemblies(source)
        model = original(parser_source, source_name)
        if not assemblies:
            return model

        assembly_ir = validate_assemblies(model.program, model.machines, assemblies)

        # CompilationModel is a frozen dataclass but intentionally has no slots.
        # The compatibility shim adds opt-in fields without changing legacy tuple
        # construction. Plain sources return the original model unchanged.
        object.__setattr__(model, "assemblies", assemblies)
        object.__setattr__(model, "assembly_ir", assembly_ir)
        object.__setattr__(model, "assembly_source", source)
        object.__setattr__(model.expanded, "assemblies", assemblies)
        object.__setattr__(model.expanded, "assembly_ir", assembly_ir)
        return model

    parse_compilation_model_with_assemblies.__name__ = original.__name__
    parse_compilation_model_with_assemblies.__qualname__ = original.__qualname__
    parse_compilation_model_with_assemblies.__doc__ = original.__doc__
    parse_compilation_model_with_assemblies.__glyph_machine_assembly__ = True
    parse_compilation_model_with_assemblies.__glyph_original__ = original

    _patch_function_references(original, parse_compilation_model_with_assemblies)
    artifacts_module.parse_compilation_model = parse_compilation_model_with_assemblies

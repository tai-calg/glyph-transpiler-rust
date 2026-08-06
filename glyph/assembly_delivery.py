from __future__ import annotations

import sys
from typing import Callable

from . import assembly as _assembly_module
from .assembly import extract_assemblies, validate_assemblies
from .compiler import TypeRef


_BUILTIN_TYPE_NAMES = {
    "R": "Result",
    "O": "Option",
    "V": "Vec",
    "S": "String",
}


def _install_assembly_type_canonicalization() -> None:
    current = _assembly_module._resolve_alias
    if getattr(current, "__glyph_assembly_type_canonical__", False):
        return
    original = current

    def canonical_type(ty: TypeRef, aliases) -> TypeRef:
        resolved = original(ty, aliases)
        return TypeRef(
            _BUILTIN_TYPE_NAMES.get(resolved.name, resolved.name),
            tuple(canonical_type(argument, aliases) for argument in resolved.args),
        )

    canonical_type.__glyph_assembly_type_canonical__ = True
    canonical_type.__glyph_original__ = original
    _assembly_module._resolve_alias = canonical_type


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


def _has_top_level_assembly(source: str) -> bool:
    for original in source.splitlines():
        clean = original.split("#", 1)[0].rstrip()
        if clean and not original[0].isspace() and clean.startswith("assembly "):
            return True
    return False


def install_machine_assembly_delivery() -> None:
    """Install assembly extraction ahead of the canonical compilation parser.

    This is an integration shim for the first implementation slice. It leaves the
    established CompilationModel constructor untouched, preserves all source line
    numbers by blanking assembly blocks, and attaches validated assembly data only
    when the source opts into assembly syntax.
    """

    from . import artifacts as artifacts_module

    _install_assembly_type_canonicalization()

    current = artifacts_module.parse_compilation_model
    if getattr(current, "__glyph_machine_assembly__", False):
        return
    original = current

    def parse_compilation_model_with_assemblies(
        source: str,
        source_name: str = "input.glyph",
    ):
        # Plain Glyph follows the exact original function with the exact original
        # source string. No split/join normalization or model mutation occurs.
        if not _has_top_level_assembly(source):
            return original(source, source_name)

        parser_source, assemblies = extract_assemblies(source)
        model = original(parser_source, source_name)
        assembly_ir = validate_assemblies(
            model.program,
            model.machines,
            assemblies,
            model.inline_effects,
        )

        # CompilationModel is a frozen dataclass but intentionally has no slots.
        # The compatibility shim adds opt-in fields without changing legacy tuple
        # construction.
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

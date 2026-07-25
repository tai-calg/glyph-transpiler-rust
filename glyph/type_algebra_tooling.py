from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

from .compiler import Field, FunctionDecl, ProductDecl, Program, SumDecl, TypeRef, Variant
from .execution_ir import ExecutionStructureIR
from .machine import MachineDecl
from .pipeline import _render_type
from .type_algebra_impl import TypeAlgebraIR


@dataclass(frozen=True)
class TypeAlgebraDiagnostic:
    code: str
    severity: str
    message: str
    subject: str
    line: int


@dataclass(frozen=True)
class StructuralStep:
    law: str
    before: str
    after: str


@dataclass(frozen=True)
class StructuralConversion:
    source_type: str
    target_type: str
    forward_function: str
    reverse_function: str
    generated: bool
    reason: str | None
    steps: tuple[StructuralStep, ...]
    rust: str


@dataclass(frozen=True)
class MachineCoverage:
    machine: str
    state_type: str
    input_types: tuple[str, ...]
    state_cardinality: str | None
    input_cardinality: str | None
    possible_pairs: str | None
    defined_pairs: int
    missing_pairs: str | None
    complete: bool | None
    reason: str | None


def _snake(name: str) -> str:
    out: list[str] = []
    for index, ch in enumerate(name):
        if ch.isupper() and index and (not name[index - 1].isupper()):
            out.append("_")
        out.append(ch.lower() if ch.isalnum() else "_")
    return "".join(out).strip("_") or "type"


def _type_map(ir: TypeAlgebraIR) -> dict[str, object]:
    return {item.name: item for item in ir.types}


def build_type_algebra_diagnostics(program: Program, ir: TypeAlgebraIR) -> tuple[TypeAlgebraDiagnostic, ...]:
    analyses = _type_map(ir)
    diagnostics: list[TypeAlgebraDiagnostic] = []
    for analysis in ir.types:
        if analysis.impossible:
            diagnostics.append(
                TypeAlgebraDiagnostic(
                    code="type-algebra-impossible",
                    severity="warning",
                    message=f"型 `{analysis.name}` の値数は0であり、構築できない",
                    subject=analysis.name,
                    line=analysis.source.line,
                )
            )
    for declaration in program.declarations:
        if not isinstance(declaration, FunctionDecl):
            continue
        impossible_params = [
            parameter.name
            for parameter in declaration.params
            if getattr(analyses.get(parameter.ty.name), "impossible", False)
        ]
        if impossible_params:
            diagnostics.append(
                TypeAlgebraDiagnostic(
                    code="type-algebra-unreachable-function",
                    severity="warning",
                    message=(
                        f"関数 `{declaration.name}` は構築不能な引数 "
                        + ", ".join(f"`{name}`" for name in impossible_params)
                        + " を要求するため呼出し不能"
                    ),
                    subject=declaration.name,
                    line=declaration.line,
                )
            )
        if getattr(analyses.get(declaration.return_type.name), "impossible", False):
            diagnostics.append(
                TypeAlgebraDiagnostic(
                    code="type-algebra-impossible-result",
                    severity="warning",
                    message=f"関数 `{declaration.name}` の戻り型 `{declaration.return_type.name}` は構築不能",
                    subject=declaration.name,
                    line=declaration.line,
                )
            )
    return tuple(diagnostics)


def _field_signature(fields: Sequence[Field]) -> tuple[tuple[str, str], ...]:
    return tuple((field.name, _render_type(field.ty)) for field in fields)


def _variant_fields(variant: Variant) -> tuple[Field, ...] | None:
    if variant.fields:
        return variant.fields
    if variant.tuple_types:
        return None
    return ()


def _render_structural_pair(
    source: ProductDecl,
    choice_field: Field,
    choice: SumDecl,
    target: SumDecl,
    payload_products: Sequence[ProductDecl],
) -> str:
    common = tuple(field for field in source.fields if field.name != choice_field.name)
    forward = f"glyph_distribute_{_snake(source.name)}_to_{_snake(target.name)}"
    reverse = f"glyph_factor_{_snake(target.name)}_to_{_snake(source.name)}"
    lines = [
        f"pub fn {forward}(value: {source.name}) -> {target.name} {{",
        f"    let {source.name} {{ "
        + ", ".join(field.name for field in source.fields)
        + " } = value;",
        f"    match {choice_field.name} {{",
    ]
    for choice_variant, target_variant, product_decl in zip(
        choice.variants, target.variants, payload_products
    ):
        fields = _variant_fields(choice_variant) or ()
        pattern = (
            f"{choice.name}::{choice_variant.name}"
            if not fields
            else f"{choice.name}::{choice_variant.name} {{ "
            + ", ".join(field.name for field in fields)
            + " }"
        )
        constructor_fields = [field.name for field in common] + [field.name for field in fields]
        lines.append(
            f"        {pattern} => {target.name}::{target_variant.name}("
            f"{product_decl.name} {{ "
            + ", ".join(f"{name}: {name}" for name in constructor_fields)
            + " }),"
        )
    lines.extend(["    }", "}", "", f"pub fn {reverse}(value: {target.name}) -> {source.name} {{", "    match value {"])
    for choice_variant, target_variant, product_decl in zip(
        choice.variants, target.variants, payload_products
    ):
        fields = _variant_fields(choice_variant) or ()
        names = [field.name for field in common] + [field.name for field in fields]
        choice_constructor = (
            f"{choice.name}::{choice_variant.name}"
            if not fields
            else f"{choice.name}::{choice_variant.name} {{ "
            + ", ".join(f"{field.name}: {field.name}" for field in fields)
            + " }"
        )
        source_values = []
        for field in source.fields:
            source_values.append(
                f"{field.name}: {choice_constructor}"
                if field.name == choice_field.name
                else f"{field.name}: {field.name}"
            )
        lines.append(
            f"        {target.name}::{target_variant.name}({product_decl.name} {{ "
            + ", ".join(names)
            + f" }}) => {source.name} {{ "
            + ", ".join(source_values)
            + " },"
        )
    lines.extend(["    }", "}", ""])
    return "\n".join(lines)


def build_structural_conversions(program: Program) -> tuple[StructuralConversion, ...]:
    products = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, ProductDecl)
    }
    sums = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, SumDecl)
    }
    results: list[StructuralConversion] = []
    for source in products.values():
        for choice_field in source.fields:
            choice = sums.get(choice_field.ty.name)
            if choice is None or choice_field.ty.args:
                continue
            if any(_variant_fields(variant) is None for variant in choice.variants):
                continue
            common = tuple(field for field in source.fields if field.name != choice_field.name)
            for target in sums.values():
                if len(target.variants) != len(choice.variants):
                    continue
                payload_products: list[ProductDecl] = []
                valid = True
                for choice_variant, target_variant in zip(choice.variants, target.variants):
                    if len(target_variant.tuple_types) != 1 or target_variant.fields:
                        valid = False
                        break
                    payload = products.get(target_variant.tuple_types[0].name)
                    variant_fields = _variant_fields(choice_variant)
                    if payload is None or variant_fields is None:
                        valid = False
                        break
                    expected = _field_signature((*common, *variant_fields))
                    if _field_signature(payload.fields) != expected:
                        valid = False
                        break
                    payload_products.append(payload)
                if not valid:
                    continue
                before = f"{source.name} = " + " * ".join(
                    _render_type(field.ty) for field in source.fields
                )
                after = f"{target.name} = " + " + ".join(
                    product_decl.name for product_decl in payload_products
                )
                forward = f"glyph_distribute_{_snake(source.name)}_to_{_snake(target.name)}"
                reverse = f"glyph_factor_{_snake(target.name)}_to_{_snake(source.name)}"
                results.append(
                    StructuralConversion(
                        source_type=source.name,
                        target_type=target.name,
                        forward_function=forward,
                        reverse_function=reverse,
                        generated=True,
                        reason=None,
                        steps=(
                            StructuralStep("distribute", before, after),
                            StructuralStep("factor", after, before),
                        ),
                        rust=_render_structural_pair(
                            source, choice_field, choice, target, payload_products
                        ),
                    )
                )
    unique: dict[tuple[str, str], StructuralConversion] = {}
    for item in results:
        unique[(item.source_type, item.target_type)] = item
    return tuple(unique[key] for key in sorted(unique))


def render_structural_conversion_rust(conversions: Sequence[StructuralConversion]) -> str:
    generated = [item.rust for item in conversions if item.generated and item.rust]
    if not generated:
        return ""
    return (
        "\n// Structural type-isomorphism conversions.\n"
        "// Generated only from a checked distributive/factoring proof.\n"
        + "\n".join(generated)
    )


def build_machine_coverage(
    program: Program,
    machines: Sequence[MachineDecl],
    execution_ir: ExecutionStructureIR,
    algebra: TypeAlgebraIR,
) -> tuple[MachineCoverage, ...]:
    analyses = _type_map(algebra)
    execution = {machine.name: machine for machine in execution_ir.machines}
    products = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, ProductDecl)
    }
    rows: list[MachineCoverage] = []
    for machine in machines:
        state_decl = products.get(machine.state_param.ty.name)
        state_analysis = analyses.get(machine.state_param.ty.name)
        input_analyses = [analyses.get(parameter.ty.name) for parameter in machine.input_params]
        state_cardinality = getattr(state_analysis, "cardinality", None)
        input_cardinality_value = 1
        exact_inputs = True
        for analysis in input_analyses:
            cardinality = getattr(analysis, "cardinality", None)
            if cardinality is None:
                exact_inputs = False
                break
            input_cardinality_value *= int(cardinality)
        input_cardinality = str(input_cardinality_value) if exact_inputs else None
        possible = (
            str(int(state_cardinality) * input_cardinality_value)
            if state_cardinality is not None and exact_inputs
            else None
        )
        view = execution.get(machine.name)
        defined = len({(item.source_state, item.condition) for item in view.transitions}) if view else 0
        missing = str(max(0, int(possible) - defined)) if possible is not None else None
        rows.append(
            MachineCoverage(
                machine=machine.name,
                state_type=state_decl.name if state_decl else machine.state_param.ty.name,
                input_types=tuple(_render_type(parameter.ty) for parameter in machine.input_params),
                state_cardinality=state_cardinality,
                input_cardinality=input_cardinality,
                possible_pairs=possible,
                defined_pairs=defined,
                missing_pairs=missing,
                complete=(defined == int(possible)) if possible is not None else None,
                reason=(
                    None
                    if possible is not None
                    else "state or input domain is not an exact finite type"
                ),
            )
        )
    return tuple(rows)


def tooling_payload(
    diagnostics: Sequence[TypeAlgebraDiagnostic],
    structural: Sequence[StructuralConversion],
    machine_coverage: Sequence[MachineCoverage] = (),
) -> dict[str, object]:
    return {
        "schema": "glyph.type-algebra-tooling",
        "version": 1,
        "diagnostics": [asdict(item) for item in diagnostics],
        "structural_conversions": [asdict(item) for item in structural],
        "machine_coverage": [asdict(item) for item in machine_coverage],
    }

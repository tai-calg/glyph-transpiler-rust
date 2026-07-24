from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product as cartesian_product
import re
from typing import Mapping, Sequence

from .compiler import AliasDecl, ProductDecl, Program, SumDecl, TypeRef, Variant
from .pipeline import _render_type


_SCHEMA = "glyph.type-algebra-ir"
_VERSION = 1
_DEFAULT_EXHAUSTIVE_LIMIT = 64

_FINITE_BUILTINS: dict[str, int] = {
    "Never": 0,
    "Unit": 1,
    "()": 1,
    "bool": 2,
    "u8": 1 << 8,
    "i8": 1 << 8,
    "u16": 1 << 16,
    "i16": 1 << 16,
    "u32": 1 << 32,
    "i32": 1 << 32,
    "u64": 1 << 64,
    "i64": 1 << 64,
    "u128": 1 << 128,
    "i128": 1 << 128,
    "f32": 1 << 32,
    "f64": 1 << 64,
}
_OPTION_NAMES = {"O", "Option"}
_RESULT_NAMES = {"R", "Result"}


@dataclass(frozen=True)
class TypeAlgebraSourceRef:
    line: int
    column: int = 1


@dataclass(frozen=True)
class AlgebraMonomial:
    coefficient: str
    factors: tuple[str, ...]


@dataclass(frozen=True)
class ExhaustiveCase:
    ordinal: int
    rust: str


@dataclass(frozen=True)
class TypeAlgebraType:
    name: str
    declaration_kind: str
    expression: str
    normal_form: str
    monomials: tuple[AlgebraMonomial, ...]
    cardinality: str | None
    cardinality_exact: bool
    impossible: bool
    exhaustive_complete: bool
    exhaustive_cases: tuple[ExhaustiveCase, ...]
    source: TypeAlgebraSourceRef


@dataclass(frozen=True)
class ConversionFunction:
    name: str
    source_type: str
    target_type: str
    strategy: str
    generated: bool
    reason: str | None = None


@dataclass(frozen=True)
class IsomorphismClass:
    id: str
    members: tuple[str, ...]
    normal_form: str
    cardinality: str | None
    conversions: tuple[str, ...]


@dataclass(frozen=True)
class TypeAlgebraIR:
    source_name: str
    exhaustive_limit: int
    types: tuple[TypeAlgebraType, ...]
    isomorphism_classes: tuple[IsomorphismClass, ...]
    conversions: tuple[ConversionFunction, ...]

    def to_dict(self) -> dict[str, object]:
        return {"schema": _SCHEMA, "version": _VERSION, **asdict(self)}


Polynomial = dict[tuple[str, ...], int]


def _poly_zero() -> Polynomial:
    return {}


def _poly_one() -> Polynomial:
    return {(): 1}


def _poly_atom(name: str) -> Polynomial:
    return {(name,): 1}


def _poly_add(left: Polynomial, right: Polynomial) -> Polynomial:
    result = dict(left)
    for factors, coefficient in right.items():
        result[factors] = result.get(factors, 0) + coefficient
        if result[factors] == 0:
            del result[factors]
    return result


def _poly_mul(left: Polynomial, right: Polynomial) -> Polynomial:
    if not left or not right:
        return {}
    result: Polynomial = {}
    for left_factors, left_coefficient in left.items():
        for right_factors, right_coefficient in right.items():
            factors = tuple(sorted((*left_factors, *right_factors)))
            result[factors] = (
                result.get(factors, 0) + left_coefficient * right_coefficient
            )
    return result


def _poly_key(poly: Polynomial) -> tuple[tuple[tuple[str, ...], int], ...]:
    return tuple(sorted(poly.items()))


def _render_polynomial(poly: Polynomial) -> str:
    if not poly:
        return "0"
    terms: list[str] = []
    for factors, coefficient in sorted(poly.items(), key=lambda item: item[0]):
        if not factors:
            terms.append(str(coefficient))
            continue
        factor_text = " * ".join(factors)
        terms.append(
            factor_text if coefficient == 1 else f"{coefficient} * {factor_text}"
        )
    return " + ".join(terms)


def _monomials(poly: Polynomial) -> tuple[AlgebraMonomial, ...]:
    return tuple(
        AlgebraMonomial(str(coefficient), factors)
        for factors, coefficient in sorted(poly.items(), key=lambda item: item[0])
    )


def _declaration_maps(
    program: Program,
) -> tuple[
    dict[str, ProductDecl],
    dict[str, SumDecl],
    dict[str, AliasDecl],
]:
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
    aliases = {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, AliasDecl)
    }
    return products, sums, aliases


class _Analyzer:
    def __init__(self, program: Program, exhaustive_limit: int):
        self.program = program
        self.exhaustive_limit = exhaustive_limit
        self.products, self.sums, self.aliases = _declaration_maps(program)
        self.declarations = {
            **self.products,
            **self.sums,
            **self.aliases,
        }
        self._poly_memo: dict[str, Polynomial] = {}
        self._value_memo: dict[str, tuple[str, ...] | None] = {}

    def polynomial_for_name(
        self,
        name: str,
        stack: frozenset[str] = frozenset(),
    ) -> Polynomial:
        if name in self._poly_memo:
            return self._poly_memo[name]
        if name in stack:
            return _poly_atom(f"recursive<{name}>")
        declaration = self.declarations.get(name)
        if declaration is None:
            return self.polynomial_for_ref(TypeRef(name), stack)
        next_stack = stack | {name}
        if isinstance(declaration, ProductDecl):
            result = _poly_one()
            for field in declaration.fields:
                result = _poly_mul(
                    result,
                    self.polynomial_for_ref(field.ty, next_stack),
                )
        elif isinstance(declaration, SumDecl):
            result = _poly_zero()
            for variant in declaration.variants:
                result = _poly_add(
                    result,
                    self.polynomial_for_variant(variant, next_stack),
                )
        else:
            result = self.polynomial_for_ref(declaration.target, next_stack)
        self._poly_memo[name] = result
        return result

    def polynomial_for_variant(
        self,
        variant: Variant,
        stack: frozenset[str],
    ) -> Polynomial:
        result = _poly_one()
        for ty in variant.tuple_types:
            result = _poly_mul(result, self.polynomial_for_ref(ty, stack))
        for field in variant.fields:
            result = _poly_mul(result, self.polynomial_for_ref(field.ty, stack))
        return result

    def polynomial_for_ref(
        self,
        ty: TypeRef,
        stack: frozenset[str] = frozenset(),
    ) -> Polynomial:
        if ty.name in self.declarations and not ty.args:
            return self.polynomial_for_name(ty.name, stack)
        if ty.name == "tuple":
            result = _poly_one()
            for argument in ty.args:
                result = _poly_mul(result, self.polynomial_for_ref(argument, stack))
            return result
        if ty.name in _OPTION_NAMES and len(ty.args) == 1:
            return _poly_add(
                _poly_one(),
                self.polynomial_for_ref(ty.args[0], stack),
            )
        if ty.name in _RESULT_NAMES and len(ty.args) == 2:
            return _poly_add(
                self.polynomial_for_ref(ty.args[0], stack),
                self.polynomial_for_ref(ty.args[1], stack),
            )
        builtin = _FINITE_BUILTINS.get(ty.name)
        if builtin is not None and not ty.args:
            return {(): builtin} if builtin else {}
        return _poly_atom(_render_type(ty))

    def values_for_name(
        self,
        name: str,
        stack: frozenset[str] = frozenset(),
    ) -> tuple[str, ...] | None:
        if name in self._value_memo:
            return self._value_memo[name]
        if name in stack:
            return None
        declaration = self.declarations.get(name)
        if declaration is None:
            return self.values_for_ref(TypeRef(name), stack)
        next_stack = stack | {name}
        if isinstance(declaration, ProductDecl):
            fields = [
                self.values_for_ref(field.ty, next_stack)
                for field in declaration.fields
            ]
            values = self._product_values(fields)
            if values is None:
                result = None
            else:
                result = tuple(
                    f"{name} {{ "
                    + ", ".join(
                        f"{field.name}: {value}"
                        for field, value in zip(declaration.fields, combination)
                    )
                    + " }"
                    for combination in values
                )
        elif isinstance(declaration, SumDecl):
            output: list[str] = []
            result: tuple[str, ...] | None = ()
            for variant in declaration.variants:
                payload_types = (
                    list(variant.tuple_types)
                    if variant.tuple_types
                    else [field.ty for field in variant.fields]
                )
                payload_values = self._product_values(
                    [
                        self.values_for_ref(ty, next_stack)
                        for ty in payload_types
                    ]
                )
                if payload_values is None:
                    result = None
                    break
                for combination in payload_values:
                    if variant.tuple_types:
                        output.append(
                            f"{name}::{variant.name}("
                            + ", ".join(combination)
                            + ")"
                        )
                    elif variant.fields:
                        output.append(
                            f"{name}::{variant.name} {{ "
                            + ", ".join(
                                f"{field.name}: {value}"
                                for field, value in zip(
                                    variant.fields,
                                    combination,
                                )
                            )
                            + " }"
                        )
                    else:
                        output.append(f"{name}::{variant.name}")
                    if len(output) > self.exhaustive_limit:
                        result = None
                        break
                if result is None:
                    break
            else:
                result = tuple(output)
        else:
            result = self.values_for_ref(declaration.target, next_stack)
        self._value_memo[name] = result
        return result

    def values_for_ref(
        self,
        ty: TypeRef,
        stack: frozenset[str] = frozenset(),
    ) -> tuple[str, ...] | None:
        if ty.name in self.declarations and not ty.args:
            return self.values_for_name(ty.name, stack)
        if ty.name == "Never" and not ty.args:
            return ()
        if ty.name in {"Unit", "()"} and not ty.args:
            return ("()",) if self.exhaustive_limit >= 1 else None
        if ty.name == "bool" and not ty.args:
            return (
                ("false", "true")
                if self.exhaustive_limit >= 2
                else None
            )
        if ty.name == "tuple":
            combinations = self._product_values(
                [self.values_for_ref(argument, stack) for argument in ty.args]
            )
            if combinations is None:
                return None
            return tuple(
                "("
                + ", ".join(combination)
                + ("," if len(combination) == 1 else "")
                + ")"
                for combination in combinations
            )
        if ty.name in _OPTION_NAMES and len(ty.args) == 1:
            inner = self.values_for_ref(ty.args[0], stack)
            if inner is None or len(inner) + 1 > self.exhaustive_limit:
                return None
            return ("None", *(f"Some({value})" for value in inner))
        if ty.name in _RESULT_NAMES and len(ty.args) == 2:
            ok_values = self.values_for_ref(ty.args[0], stack)
            err_values = self.values_for_ref(ty.args[1], stack)
            if ok_values is None or err_values is None:
                return None
            if len(ok_values) + len(err_values) > self.exhaustive_limit:
                return None
            return tuple(
                [
                    *(f"Ok({value})" for value in ok_values),
                    *(f"Err({value})" for value in err_values),
                ]
            )
        return None

    def _product_values(
        self,
        factors: Sequence[tuple[str, ...] | None],
    ) -> tuple[tuple[str, ...], ...] | None:
        if any(factor is None for factor in factors):
            return None
        exact = [factor for factor in factors if factor is not None]
        cardinality = 1
        for factor in exact:
            cardinality *= len(factor)
            if cardinality > self.exhaustive_limit:
                return None
        return tuple(cartesian_product(*exact)) if exact else ((),)


def _declaration_kind(declaration: object) -> str:
    if isinstance(declaration, ProductDecl):
        return "product"
    if isinstance(declaration, SumDecl):
        return "sum"
    return "alias"


def _declaration_expression(declaration: object) -> str:
    if isinstance(declaration, ProductDecl):
        if not declaration.fields:
            return "1"
        return " * ".join(_render_type(field.ty) for field in declaration.fields)
    if isinstance(declaration, SumDecl):
        terms: list[str] = []
        for variant in declaration.variants:
            payload = [
                *variant.tuple_types,
                *(field.ty for field in variant.fields),
            ]
            terms.append(
                "1"
                if not payload
                else " * ".join(_render_type(ty) for ty in payload)
            )
        return " + ".join(terms) if terms else "0"
    assert isinstance(declaration, AliasDecl)
    return _render_type(declaration.target)


def _snake(name: str) -> str:
    separated = re.sub(r"(?<!^)(?=[A-Z])", "_", name)
    return (
        re.sub(r"[^A-Za-z0-9_]+", "_", separated)
        .strip("_")
        .lower()
        or "type"
    )


def _conversion_name(source: str, target: str) -> str:
    return f"glyph_convert_{_snake(source)}_to_{_snake(target)}"


def build_type_algebra_ir(
    source_name: str,
    program: Program,
    *,
    exhaustive_limit: int = _DEFAULT_EXHAUSTIVE_LIMIT,
) -> TypeAlgebraIR:
    """Normalize pure data declarations as a commutative semiring.

    `+` is sum type, `*` is product type, `Never` is zero, and `Unit`/`()``
    is one. Unknown and recursive references remain symbolic atoms, so the
    analysis is conservative rather than inventing an isomorphism.
    """

    if exhaustive_limit < 0:
        raise ValueError("exhaustive_limit must be non-negative")
    analyzer = _Analyzer(program, exhaustive_limit)
    analyses: list[TypeAlgebraType] = []
    analysis_by_name: dict[str, TypeAlgebraType] = {}

    for declaration in program.declarations:
        if not isinstance(declaration, (ProductDecl, SumDecl, AliasDecl)):
            continue
        polynomial = analyzer.polynomial_for_name(declaration.name)
        exact = all(not factors for factors in polynomial)
        cardinality = sum(polynomial.values()) if exact else None
        values = analyzer.values_for_name(declaration.name)
        exhaustive_complete = values is not None and (
            cardinality is not None and len(values) == cardinality
        )
        cases = (
            tuple(
                ExhaustiveCase(index, value)
                for index, value in enumerate(values)
            )
            if exhaustive_complete and values is not None
            else ()
        )
        analysis = TypeAlgebraType(
            name=declaration.name,
            declaration_kind=_declaration_kind(declaration),
            expression=_declaration_expression(declaration),
            normal_form=_render_polynomial(polynomial),
            monomials=_monomials(polynomial),
            cardinality=None if cardinality is None else str(cardinality),
            cardinality_exact=exact,
            impossible=not polynomial,
            exhaustive_complete=exhaustive_complete,
            exhaustive_cases=cases,
            source=TypeAlgebraSourceRef(declaration.line),
        )
        analyses.append(analysis)
        analysis_by_name[analysis.name] = analysis

    grouped: dict[tuple[tuple[tuple[str, ...], int], ...], list[str]] = {}
    for analysis in analyses:
        polynomial = analyzer.polynomial_for_name(analysis.name)
        grouped.setdefault(_poly_key(polynomial), []).append(analysis.name)

    conversions: list[ConversionFunction] = []
    classes: list[IsomorphismClass] = []
    class_index = 0
    for _, members_value in sorted(grouped.items(), key=lambda item: item[1]):
        members = tuple(sorted(members_value))
        if len(members) < 2:
            continue
        class_index += 1
        class_conversion_names: list[str] = []
        for left_index, left in enumerate(members):
            for right in members[left_index + 1 :]:
                left_analysis = analysis_by_name[left]
                right_analysis = analysis_by_name[right]
                can_generate = (
                    left_analysis.exhaustive_complete
                    and right_analysis.exhaustive_complete
                    and left_analysis.cardinality not in {None, "0"}
                    and left_analysis.cardinality == right_analysis.cardinality
                )
                reason = (
                    None
                    if can_generate
                    else (
                        "conversion requires a non-empty exact finite type "
                        f"with at most {exhaustive_limit} values"
                    )
                )
                for source, target in ((left, right), (right, left)):
                    name = _conversion_name(source, target)
                    conversions.append(
                        ConversionFunction(
                            name=name,
                            source_type=source,
                            target_type=target,
                            strategy="deterministic-finite-bijection",
                            generated=can_generate,
                            reason=reason,
                        )
                    )
                    if can_generate:
                        class_conversion_names.append(name)
        first = analysis_by_name[members[0]]
        classes.append(
            IsomorphismClass(
                id=f"iso_{class_index:03d}",
                members=members,
                normal_form=first.normal_form,
                cardinality=first.cardinality,
                conversions=tuple(class_conversion_names),
            )
        )

    return TypeAlgebraIR(
        source_name=source_name,
        exhaustive_limit=exhaustive_limit,
        types=tuple(analyses),
        isomorphism_classes=tuple(classes),
        conversions=tuple(conversions),
    )


def render_type_algebra_rust(ir: TypeAlgebraIR) -> str:
    """Generate bounded conversion functions and exhaustive Rust tests."""

    analyses = {analysis.name: analysis for analysis in ir.types}
    lines = [
        "// @generated by Glyph type algebra. Do not edit by hand.",
        "// Conversions are deterministic finite-set bijections, not semantic renamings.",
        "use crate::generated::*;",
        "",
    ]
    generated = [
        conversion for conversion in ir.conversions if conversion.generated
    ]
    for conversion in generated:
        source_cases = analyses[conversion.source_type].exhaustive_cases
        target_cases = analyses[conversion.target_type].exhaustive_cases
        lines.append(
            f"pub fn {conversion.name}(value: {conversion.source_type}) "
            f"-> {conversion.target_type} {{"
        )
        lines.append("    match value {")
        for source_case, target_case in zip(source_cases, target_cases):
            lines.append(f"        {source_case.rust} => {target_case.rust},")
        lines.extend(["    }", "}", ""])

    testable = [
        analysis
        for analysis in ir.types
        if analysis.exhaustive_complete and analysis.exhaustive_cases
    ]
    if generated or testable:
        lines.extend(
            [
                "#[cfg(test)]",
                "mod glyph_type_algebra_tests {",
                "    use super::*;",
                "",
            ]
        )
        for analysis in testable:
            values = ", ".join(
                case.rust for case in analysis.exhaustive_cases
            )
            lines.extend(
                [
                    "    #[test]",
                    f"    fn exhaustive_{_snake(analysis.name)}() {{",
                    f"        let values: Vec<{analysis.name}> = vec![{values}];",
                    f"        assert_eq!(values.len(), {analysis.cardinality});",
                    "        for left in 0..values.len() {",
                    "            for right in (left + 1)..values.len() {",
                    "                assert_ne!(values[left], values[right]);",
                    "            }",
                    "        }",
                    "    }",
                    "",
                ]
            )
        pairs: set[tuple[str, str]] = set()
        generated_by_pair = {
            (conversion.source_type, conversion.target_type): conversion
            for conversion in generated
        }
        for conversion in generated:
            reverse_key = (
                conversion.target_type,
                conversion.source_type,
            )
            pair = tuple(
                sorted((conversion.source_type, conversion.target_type))
            )
            if pair in pairs or reverse_key not in generated_by_pair:
                continue
            pairs.add(pair)
            reverse = generated_by_pair[reverse_key]
            source = analyses[conversion.source_type]
            values = ", ".join(case.rust for case in source.exhaustive_cases)
            lines.extend(
                [
                    "    #[test]",
                    (
                        "    fn roundtrip_"
                        f"{_snake(conversion.source_type)}_"
                        f"{_snake(conversion.target_type)}() {{"
                    ),
                    (
                        f"        let values: Vec<{conversion.source_type}> "
                        f"= vec![{values}];"
                    ),
                    "        for value in values {",
                    (
                        f"            let restored = {reverse.name}("
                        f"{conversion.name}(value.clone()));"
                    ),
                    "            assert_eq!(restored, value);",
                    "        }",
                    "    }",
                    "",
                ]
            )
        lines.append("}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

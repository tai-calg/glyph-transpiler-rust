from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product as cartesian_product
import re
from typing import Sequence

from .compiler import AliasDecl, ProductDecl, Program, SumDecl, TypeRef, Variant
from .pipeline import _render_type

_SCHEMA = "glyph.type-algebra-ir"
_VERSION = 1
_DEFAULT_EXHAUSTIVE_LIMIT = 64
_FINITE_CARDINALITIES = {
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


def _atom(name: str) -> Polynomial:
    return {(name,): 1}


def _add(left: Polynomial, right: Polynomial) -> Polynomial:
    result = dict(left)
    for factors, coefficient in right.items():
        result[factors] = result.get(factors, 0) + coefficient
    return {
        factors: coefficient
        for factors, coefficient in result.items()
        if coefficient
    }


def _multiply(left: Polynomial, right: Polynomial) -> Polynomial:
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
    for factors, coefficient in sorted(poly.items()):
        if not factors:
            terms.append(str(coefficient))
        else:
            factors_text = " * ".join(factors)
            terms.append(
                factors_text
                if coefficient == 1
                else f"{coefficient} * {factors_text}"
            )
    return " + ".join(terms)


def _render_monomials(poly: Polynomial) -> tuple[AlgebraMonomial, ...]:
    return tuple(
        AlgebraMonomial(str(coefficient), factors)
        for factors, coefficient in sorted(poly.items())
    )


def _declaration_maps(program: Program):
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
        self.exhaustive_limit = exhaustive_limit
        self.products, self.sums, self.aliases = _declaration_maps(program)
        self.declarations = {**self.products, **self.sums, **self.aliases}
        self._top_level_polynomials: dict[str, Polynomial] = {}
        self._top_level_values: dict[str, tuple[str, ...] | None] = {}

    def polynomial_for_name(
        self,
        name: str,
        stack: tuple[str, ...] = (),
    ) -> Polynomial:
        if not stack and name in self._top_level_polynomials:
            return self._top_level_polynomials[name]
        if name in stack:
            index = stack.index(name)
            cycle = (*stack[index:], name)
            return _atom(f"recursive<{'->'.join(cycle)}>")
        declaration = self.declarations.get(name)
        if declaration is None:
            return self.polynomial_for_ref(TypeRef(name), stack)
        next_stack = (*stack, name)
        if isinstance(declaration, ProductDecl):
            result: Polynomial = {(): 1}
            for field in declaration.fields:
                result = _multiply(
                    result,
                    self.polynomial_for_ref(field.ty, next_stack),
                )
        elif isinstance(declaration, SumDecl):
            result = {}
            for variant in declaration.variants:
                result = _add(
                    result,
                    self.polynomial_for_variant(variant, next_stack),
                )
        else:
            result = self.polynomial_for_ref(declaration.target, next_stack)
        if not stack:
            self._top_level_polynomials[name] = result
        return result

    def polynomial_for_variant(
        self,
        variant: Variant,
        stack: tuple[str, ...],
    ) -> Polynomial:
        result: Polynomial = {(): 1}
        for ty in variant.tuple_types:
            result = _multiply(result, self.polynomial_for_ref(ty, stack))
        for field in variant.fields:
            result = _multiply(result, self.polynomial_for_ref(field.ty, stack))
        return result

    def polynomial_for_ref(
        self,
        ty: TypeRef,
        stack: tuple[str, ...] = (),
    ) -> Polynomial:
        if ty.name in self.declarations and not ty.args:
            return self.polynomial_for_name(ty.name, stack)
        if ty.name == "tuple":
            result: Polynomial = {(): 1}
            for argument in ty.args:
                result = _multiply(
                    result,
                    self.polynomial_for_ref(argument, stack),
                )
            return result
        if ty.name in _OPTION_NAMES and len(ty.args) == 1:
            return _add(
                {(): 1},
                self.polynomial_for_ref(ty.args[0], stack),
            )
        if ty.name in _RESULT_NAMES and len(ty.args) == 2:
            return _add(
                self.polynomial_for_ref(ty.args[0], stack),
                self.polynomial_for_ref(ty.args[1], stack),
            )
        cardinality = _FINITE_CARDINALITIES.get(ty.name)
        if cardinality is not None and not ty.args:
            return {(): cardinality} if cardinality else {}
        return _atom(_render_type(ty))

    def values_for_name(
        self,
        name: str,
        stack: tuple[str, ...] = (),
    ) -> tuple[str, ...] | None:
        if not stack and name in self._top_level_values:
            return self._top_level_values[name]
        if name in stack:
            return None
        declaration = self.declarations.get(name)
        if declaration is None:
            return self.values_for_ref(TypeRef(name), stack)
        next_stack = (*stack, name)
        if isinstance(declaration, ProductDecl):
            combinations = self._product_values(
                [
                    self.values_for_ref(field.ty, next_stack)
                    for field in declaration.fields
                ]
            )
            result = (
                None
                if combinations is None
                else tuple(
                    f"{name} {{ "
                    + ", ".join(
                        f"{field.name}: {value}"
                        for field, value in zip(
                            declaration.fields,
                            combination,
                        )
                    )
                    + " }"
                    for combination in combinations
                )
            )
        elif isinstance(declaration, SumDecl):
            result = self._sum_values(declaration, next_stack)
        else:
            result = self.values_for_ref(declaration.target, next_stack)
        if not stack:
            self._top_level_values[name] = result
        return result

    def _sum_values(
        self,
        declaration: SumDecl,
        stack: tuple[str, ...],
    ) -> tuple[str, ...] | None:
        output: list[str] = []
        for variant in declaration.variants:
            payload_types = (
                list(variant.tuple_types)
                if variant.tuple_types
                else [field.ty for field in variant.fields]
            )
            combinations = self._product_values(
                [self.values_for_ref(ty, stack) for ty in payload_types]
            )
            if combinations is None:
                return None
            for combination in combinations:
                if variant.tuple_types:
                    value = (
                        f"{declaration.name}::{variant.name}("
                        + ", ".join(combination)
                        + ")"
                    )
                elif variant.fields:
                    value = (
                        f"{declaration.name}::{variant.name} {{ "
                        + ", ".join(
                            f"{field.name}: {item}"
                            for field, item in zip(
                                variant.fields,
                                combination,
                            )
                        )
                        + " }"
                    )
                else:
                    value = f"{declaration.name}::{variant.name}"
                output.append(value)
                if len(output) > self.exhaustive_limit:
                    return None
        return tuple(output)

    def values_for_ref(
        self,
        ty: TypeRef,
        stack: tuple[str, ...] = (),
    ) -> tuple[str, ...] | None:
        if ty.name in self.declarations and not ty.args:
            return self.values_for_name(ty.name, stack)
        if ty.name == "Never" and not ty.args:
            return ()
        if ty.name == "()" and not ty.args:
            return ("()",) if self.exhaustive_limit >= 1 else None
        if ty.name == "bool" and not ty.args:
            return (
                ("false", "true")
                if self.exhaustive_limit >= 2
                else None
            )
        if ty.name == "tuple":
            combinations = self._product_values(
                [
                    self.values_for_ref(argument, stack)
                    for argument in ty.args
                ]
            )
            if combinations is None:
                return None
            return tuple(
                "("
                + ", ".join(items)
                + ("," if len(items) == 1 else "")
                + ")"
                for items in combinations
            )
        if ty.name in _OPTION_NAMES and len(ty.args) == 1:
            inner = self.values_for_ref(ty.args[0], stack)
            if inner is None or len(inner) + 1 > self.exhaustive_limit:
                return None
            return ("None", *(f"Some({value})" for value in inner))
        if ty.name in _RESULT_NAMES and len(ty.args) == 2:
            ok_values = self.values_for_ref(ty.args[0], stack)
            error_values = self.values_for_ref(ty.args[1], stack)
            if ok_values is None or error_values is None:
                return None
            if len(ok_values) + len(error_values) > self.exhaustive_limit:
                return None
            return tuple(
                [
                    *(f"Ok({value})" for value in ok_values),
                    *(f"Err({value})" for value in error_values),
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
        return (
            " * ".join(_render_type(field.ty) for field in declaration.fields)
            or "1"
        )
    if isinstance(declaration, SumDecl):
        terms: list[str] = []
        for variant in declaration.variants:
            payload = [
                *variant.tuple_types,
                *(field.ty for field in variant.fields),
            ]
            terms.append(
                " * ".join(_render_type(ty) for ty in payload) or "1"
            )
        return " + ".join(terms) or "0"
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
    """Normalize pure data declarations under commutative-semiring laws.

    Unknown references and recursion remain symbolic atoms. Equal normal forms
    therefore establish only a structural value-set isomorphism candidate.
    """

    if exhaustive_limit < 0:
        raise ValueError("exhaustive_limit must be non-negative")
    analyzer = _Analyzer(program, exhaustive_limit)
    analyses: list[TypeAlgebraType] = []
    by_name: dict[str, TypeAlgebraType] = {}
    polynomials: dict[str, Polynomial] = {}

    for declaration in program.declarations:
        if not isinstance(declaration, (ProductDecl, SumDecl, AliasDecl)):
            continue
        polynomial = analyzer.polynomial_for_name(declaration.name)
        polynomials[declaration.name] = polynomial
        cardinality_exact = all(not factors for factors in polynomial)
        cardinality = sum(polynomial.values()) if cardinality_exact else None
        values = analyzer.values_for_name(declaration.name)
        exhaustive_complete = (
            values is not None
            and cardinality is not None
            and len(values) == cardinality
        )
        cases = (
            tuple(
                ExhaustiveCase(index, value)
                for index, value in enumerate(values or ())
            )
            if exhaustive_complete
            else ()
        )
        analysis = TypeAlgebraType(
            name=declaration.name,
            declaration_kind=_declaration_kind(declaration),
            expression=_declaration_expression(declaration),
            normal_form=_render_polynomial(polynomial),
            monomials=_render_monomials(polynomial),
            cardinality=None if cardinality is None else str(cardinality),
            cardinality_exact=cardinality_exact,
            impossible=not polynomial,
            exhaustive_complete=exhaustive_complete,
            exhaustive_cases=cases,
            source=TypeAlgebraSourceRef(declaration.line),
        )
        analyses.append(analysis)
        by_name[analysis.name] = analysis

    groups: dict[
        tuple[tuple[tuple[str, ...], int], ...],
        list[str],
    ] = {}
    for name, polynomial in polynomials.items():
        groups.setdefault(_poly_key(polynomial), []).append(name)

    classes: list[IsomorphismClass] = []
    conversions: list[ConversionFunction] = []
    grouped_names = sorted(
        (sorted(group) for group in groups.values() if len(group) >= 2)
    )
    for class_index, names in enumerate(grouped_names, start=1):
        members = tuple(names)
        generated_names: list[str] = []
        for left_index, left in enumerate(members):
            for right in members[left_index + 1 :]:
                left_analysis = by_name[left]
                right_analysis = by_name[right]
                generated = (
                    left_analysis.exhaustive_complete
                    and right_analysis.exhaustive_complete
                    and left_analysis.cardinality not in {None, "0"}
                    and left_analysis.cardinality
                    == right_analysis.cardinality
                )
                reason = (
                    None
                    if generated
                    else (
                        "conversion requires a non-empty exact finite type "
                        f"with at most {exhaustive_limit} enumerable values"
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
                            generated=generated,
                            reason=reason,
                        )
                    )
                    if generated:
                        generated_names.append(name)
        first = by_name[members[0]]
        classes.append(
            IsomorphismClass(
                id=f"iso_{class_index:03d}",
                members=members,
                normal_form=first.normal_form,
                cardinality=first.cardinality,
                conversions=tuple(generated_names),
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
    """Generate bounded finite bijections and executable exhaustive tests."""

    analyses = {analysis.name: analysis for analysis in ir.types}
    generated = [
        conversion for conversion in ir.conversions if conversion.generated
    ]
    lines = [
        "// @generated by Glyph type algebra. Do not edit by hand.",
        "// Bijections preserve enumeration identity, not domain meaning or ABI.",
        "use crate::generated::*;",
        "",
    ]
    for conversion in generated:
        source_cases = analyses[conversion.source_type].exhaustive_cases
        target_cases = analyses[conversion.target_type].exhaustive_cases
        lines.extend(
            [
                (
                    f"pub fn {conversion.name}("
                    f"value: {conversion.source_type}"
                    f") -> {conversion.target_type} {{"
                ),
                "    match value {",
                *(
                    f"        {source.rust} => {target.rust},"
                    for source, target in zip(
                        source_cases,
                        target_cases,
                    )
                ),
                "    }",
                "}",
                "",
            ]
        )

    testable = [
        analysis
        for analysis in ir.types
        if analysis.exhaustive_complete and analysis.exhaustive_cases
    ]
    if not generated and not testable:
        return "\n".join(lines).rstrip() + "\n"

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

    by_pair = {
        (conversion.source_type, conversion.target_type): conversion
        for conversion in generated
    }
    emitted_pairs: set[tuple[str, str]] = set()
    for conversion in generated:
        pair = tuple(
            sorted((conversion.source_type, conversion.target_type))
        )
        reverse = by_pair.get(
            (conversion.target_type, conversion.source_type)
        )
        if reverse is None or pair in emitted_pairs:
            continue
        emitted_pairs.add(pair)
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
    lines.extend(["}", ""])
    return "\n".join(lines).rstrip() + "\n"

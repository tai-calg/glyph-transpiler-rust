from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .compiler import (
    BinaryExpr,
    CallExpr,
    Expr,
    FunctionDecl,
    GlyphError,
    NameExpr,
    Program,
    RustGenerator,
    Variant,
)


@dataclass(frozen=True)
class _PatternArg:
    kind: str
    name: str | None = None
    value: Expr | None = None


@dataclass(frozen=True)
class _VariantGuard:
    subject: Expr
    enum_name: str
    variant: Variant
    args: tuple[_PatternArg, ...]


class PatternRustGenerator(RustGenerator):
    """Rust generator with guard-only enum variant pattern matching.

    Existing expression equality remains unchanged. A guard condition is treated as
    a pattern only when its right-hand side is a declared enum variant:

        command=Run(system.sequence)  # compare payload with an expression
        command=Run(speed)            # bind payload as `speed`
        command=Run(_)                # ignore payload
        command=Stop                  # unit variant

    Matching is performed against a clone of the subject. Generated sum types
    already derive Clone, and cloning keeps the original value available to the
    branch result.
    """

    def _function(self, decl: FunctionDecl) -> list[str]:
        if decl.expression is not None or not decl.guards:
            return super()._function(decl)

        parsed = [
            None if clause.condition is None else self._variant_guard(decl, clause.condition)
            for clause in decl.guards
        ]
        if not any(item is not None for item in parsed):
            return super()._function(decl)

        signature = f"pub fn {decl.name}{self._signature_tail(decl.params, decl.return_type)} {{"
        lines = [signature]

        for clause, pattern in zip(decl.guards, parsed):
            if clause.condition is None:
                lines.append(f"    {self._expr(clause.value)}")
                continue

            if pattern is None:
                lines.extend(
                    [
                        f"    if {self._expr(clause.condition)} {{",
                        f"        return {self._expr(clause.value)};",
                        "    }",
                    ]
                )
                continue

            lines.extend(self._pattern_branch(decl, clause.value, pattern))

        lines.extend(["}", ""])
        return lines

    def _variant_guard(self, decl: FunctionDecl, condition: Expr) -> _VariantGuard | None:
        if not isinstance(condition, BinaryExpr) or condition.op not in {"=", "=="}:
            return None

        variant_name: str
        args: Sequence[Expr]
        right = condition.right

        if isinstance(right, NameExpr):
            variant_name = right.name
            args = ()
        elif isinstance(right, CallExpr) and isinstance(right.callee, NameExpr):
            variant_name = right.callee.name
            args = right.args
        else:
            return None

        resolved = self.symbols.variants.get(variant_name)
        if resolved is None:
            return None

        enum_name, variant = resolved
        expected = len(variant.fields) if variant.fields else len(variant.tuple_types)
        if len(args) != expected:
            raise GlyphError(
                f"{decl.line}行目: variant pattern {variant_name} は{expected}引数だが"
                f"{len(args)}引数を受け取った"
            )

        params = {param.name for param in decl.params}
        binders: set[str] = set()
        parsed_args: list[_PatternArg] = []

        for arg in args:
            if isinstance(arg, NameExpr) and arg.name == "_":
                parsed_args.append(_PatternArg("wildcard"))
                continue

            # A bare identifier that is not already a function parameter binds the
            # payload. Existing parameters are value constraints. Parenthesizing a
            # bare identifier also forces value comparison because the parser no
            # longer presents it as a naked NameExpr at this point only when macros
            # or a larger expression are involved; field expressions are naturally
            # value constraints.
            if isinstance(arg, NameExpr) and arg.name not in params:
                if arg.name in binders:
                    raise GlyphError(
                        f"{decl.line}行目: variant patternの束縛名 '{arg.name}' が重複"
                    )
                if arg.name in self.symbols.variants or arg.name in self.symbols.products:
                    parsed_args.append(_PatternArg("value", value=arg))
                else:
                    binders.add(arg.name)
                    parsed_args.append(_PatternArg("bind", name=arg.name))
                continue

            parsed_args.append(_PatternArg("value", value=arg))

        return _VariantGuard(condition.left, enum_name, variant, tuple(parsed_args))

    def _pattern_branch(
        self,
        decl: FunctionDecl,
        value: Expr,
        pattern: _VariantGuard,
    ) -> list[str]:
        rust_pattern, checks, bindings = self._rust_pattern(decl, pattern)
        subject = self._expr(pattern.subject)
        lines = [f"    if let {rust_pattern} = ({subject}).clone() {{"]

        if checks:
            lines.append(f"        if {' && '.join(checks)} {{")
            for name, internal in bindings:
                lines.append(f"            let {name} = {internal};")
            lines.append(f"            return {self._expr(value)};")
            lines.append("        }")
        else:
            for name, internal in bindings:
                lines.append(f"        let {name} = {internal};")
            lines.append(f"        return {self._expr(value)};")

        lines.append("    }")
        return lines

    def _rust_pattern(
        self,
        decl: FunctionDecl,
        pattern: _VariantGuard,
    ) -> tuple[str, list[str], list[tuple[str, str]]]:
        rendered: list[str] = []
        checks: list[str] = []
        bindings: list[tuple[str, str]] = []

        for index, arg in enumerate(pattern.args):
            if arg.kind == "wildcard":
                rendered.append("_")
                continue

            internal = f"__glyph_match_{decl.line}_{index}"
            rendered.append(internal)

            if arg.kind == "bind":
                assert arg.name is not None
                bindings.append((arg.name, internal))
            elif arg.kind == "value":
                assert arg.value is not None
                checks.append(f"{internal} == {self._expr(arg.value)}")
            else:
                raise TypeError(f"unknown pattern argument kind: {arg.kind}")

        prefix = f"{pattern.enum_name}::{pattern.variant.name}"
        if pattern.variant.fields:
            fields = ", ".join(
                f"{field.name}: {item}"
                for field, item in zip(pattern.variant.fields, rendered)
            )
            return f"{prefix} {{ {fields} }}", checks, bindings
        if pattern.variant.tuple_types:
            return f"{prefix}({', '.join(rendered)})", checks, bindings
        return prefix, checks, bindings


def generate_pattern_rust(program: Program) -> str:
    return PatternRustGenerator(program).generate()

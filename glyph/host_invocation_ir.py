from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .artifacts import CompilationModel
from .compiler import (
    AliasDecl,
    BinaryExpr,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    NameExpr,
    TryExpr,
    TypeRef,
    UnaryExpr,
)
from .execution_ir import render_expr


HOST_INVOCATION_IR_SCHEMA = "glyph.host-invocation-ir"
HOST_INVOCATION_IR_VERSION = 1


def render_type(type_ref: TypeRef) -> str:
    if not type_ref.args:
        return type_ref.name
    return f"{type_ref.name}<{','.join(render_type(item) for item in type_ref.args)}>"


def resolve_alias(type_ref: TypeRef, aliases: Mapping[str, TypeRef]) -> TypeRef:
    current = type_ref
    visited: set[str] = set()
    while not current.args and current.name in aliases:
        if current.name in visited:
            break
        visited.add(current.name)
        current = aliases[current.name]
    return current


def split_result_type(
    type_ref: TypeRef,
    aliases: Mapping[str, TypeRef],
) -> tuple[TypeRef, TypeRef | None]:
    resolved = resolve_alias(type_ref, aliases)
    if resolved.name in {"R", "Result"} and len(resolved.args) == 2:
        return resolved.args[0], resolved.args[1]
    return resolved, None


@dataclass(frozen=True)
class HostInvocationSite:
    id: str
    caller: str
    effect: str
    call: str
    arguments: tuple[str, ...]
    parameter_names: tuple[str, ...]
    parameter_types: tuple[str, ...]
    success_type: str
    failure_type: str | None
    result_type: str
    source_line: int
    ordinal: int

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "caller": self.caller,
            "effect": self.effect,
            "call": self.call,
            "arguments": [
                {
                    "expression": expression,
                    "parameter": name,
                    "type": type_name,
                }
                for expression, name, type_name in zip(
                    self.arguments,
                    self.parameter_names,
                    self.parameter_types,
                    strict=True,
                )
            ],
            "success_type": self.success_type,
            "failure_type": self.failure_type,
            "result_type": self.result_type,
            "source": {"line": self.source_line, "column": 1},
            "ordinal": self.ordinal,
        }


@dataclass(frozen=True)
class ResolvedHostInvocation:
    invocation_id: str
    effect: str
    call: str
    failure_type: str | None


class HostInvocationPlan:
    """Compiler-produced inventory of all statically declared effect call sites."""

    def __init__(self, sites: Iterable[HostInvocationSite]):
        self.sites = tuple(sites)
        self._by_id = {site.id: site for site in self.sites}
        self._by_call: dict[tuple[str, str], list[HostInvocationSite]] = {}
        for site in self.sites:
            self._by_call.setdefault((site.caller, site.call), []).append(site)

    @classmethod
    def from_model(cls, model: CompilationModel) -> "HostInvocationPlan":
        externs = {
            declaration.name: declaration
            for declaration in model.program.declarations
            if isinstance(declaration, ExternDecl)
        }
        aliases = {
            declaration.name: declaration.target
            for declaration in model.program.declarations
            if isinstance(declaration, AliasDecl)
        }
        sites: list[HostInvocationSite] = []
        occurrence: dict[tuple[str, str, int], int] = {}

        def record(caller: str, line: int, call: CallExpr) -> None:
            if not isinstance(call.callee, NameExpr):
                return
            external = externs.get(call.callee.name)
            if external is None:
                return
            rendered = render_expr(call)
            key = (caller, rendered, line)
            ordinal = occurrence.get(key, 0) + 1
            occurrence[key] = ordinal
            success, failure = split_result_type(external.return_type, aliases)
            sites.append(
                HostInvocationSite(
                    id=f"H{len(sites) + 1}",
                    caller=caller,
                    effect=external.name,
                    call=rendered,
                    arguments=tuple(render_expr(argument) for argument in call.args),
                    parameter_names=tuple(parameter.name for parameter in external.params),
                    parameter_types=tuple(render_type(parameter.ty) for parameter in external.params),
                    success_type=render_type(success),
                    failure_type=None if failure is None else render_type(failure),
                    result_type=render_type(external.return_type),
                    source_line=line,
                    ordinal=ordinal,
                )
            )

        for declaration in model.program.declarations:
            if not isinstance(declaration, FunctionDecl):
                continue
            if declaration.expression is not None:
                for call in _direct_effect_calls(declaration.expression, externs):
                    record(declaration.name, declaration.line, call)
            for clause in declaration.guards:
                for call in _direct_effect_calls(clause.value, externs):
                    record(declaration.name, clause.line, call)
        return cls(sites)

    def site(self, invocation_id: str) -> HostInvocationSite:
        try:
            return self._by_id[invocation_id]
        except KeyError as exc:
            raise KeyError(f"unknown HostInvocationIR id '{invocation_id}'") from exc

    def resolve_site(
        self,
        caller: str,
        call: str,
        *,
        source_line: int | None = None,
    ) -> HostInvocationSite | None:
        candidates = self._by_call.get((caller, call), ())
        if source_line is not None:
            exact = [site for site in candidates if site.source_line == source_line]
            if exact:
                return exact[0]
        return candidates[0] if candidates else None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": HOST_INVOCATION_IR_SCHEMA,
            "version": HOST_INVOCATION_IR_VERSION,
            "invocations": [site.to_dict() for site in self.sites],
        }


def _direct_effect_calls(
    expression: Expr,
    externs: Mapping[str, ExternDecl],
) -> Iterable[CallExpr]:
    """Yield direct effect calls in runtime evaluation order."""

    if isinstance(expression, UnaryExpr):
        yield from _direct_effect_calls(expression.expr, externs)
        return
    if isinstance(expression, TryExpr):
        yield from _direct_effect_calls(expression.expr, externs)
        return
    if isinstance(expression, BinaryExpr):
        yield from _direct_effect_calls(expression.left, externs)
        yield from _direct_effect_calls(expression.right, externs)
        return
    if isinstance(expression, FieldExpr):
        yield from _direct_effect_calls(expression.base, externs)
        return
    if not isinstance(expression, CallExpr):
        return
    yield from _direct_effect_calls(expression.callee, externs)
    for argument in expression.args:
        yield from _direct_effect_calls(argument, externs)
    if isinstance(expression.callee, NameExpr) and expression.callee.name in externs:
        yield expression


def _substitute(expression: Expr, bindings: Mapping[str, Expr]) -> Expr:
    if isinstance(expression, NameExpr):
        return bindings.get(expression.name, expression)
    if isinstance(expression, UnaryExpr):
        return UnaryExpr(expression.op, _substitute(expression.expr, bindings))
    if isinstance(expression, TryExpr):
        return TryExpr(_substitute(expression.expr, bindings))
    if isinstance(expression, BinaryExpr):
        return BinaryExpr(
            expression.op,
            _substitute(expression.left, bindings),
            _substitute(expression.right, bindings),
        )
    if isinstance(expression, FieldExpr):
        return FieldExpr(_substitute(expression.base, bindings), expression.field)
    if isinstance(expression, CallExpr):
        return CallExpr(
            _substitute(expression.callee, bindings),
            tuple(_substitute(argument, bindings) for argument in expression.args),
        )
    return expression


def resolve_invocations_in_expr(
    expression: Expr,
    *,
    caller: str,
    source_line: int,
    functions: Mapping[str, FunctionDecl],
    externs: Mapping[str, ExternDecl],
    plan: HostInvocationPlan,
    bindings: Mapping[str, Expr] | None = None,
    visited: tuple[str, ...] = (),
) -> tuple[ResolvedHostInvocation, ...]:
    """Resolve reachable effect sites without reparsing rendered source.

    Pure single-expression helpers are followed with their actual arguments
    substituted. Guarded helpers are not guessed because their selected clause must
    already have been resolved by the state-transition compiler.
    """

    environment = {} if bindings is None else dict(bindings)
    resolved: list[ResolvedHostInvocation] = []

    def visit(node: Expr, owner: str, line: int, local_bindings: Mapping[str, Expr]) -> None:
        if isinstance(node, UnaryExpr):
            visit(node.expr, owner, line, local_bindings)
            return
        if isinstance(node, TryExpr):
            visit(node.expr, owner, line, local_bindings)
            return
        if isinstance(node, BinaryExpr):
            visit(node.left, owner, line, local_bindings)
            visit(node.right, owner, line, local_bindings)
            return
        if isinstance(node, FieldExpr):
            visit(node.base, owner, line, local_bindings)
            return
        if not isinstance(node, CallExpr):
            return

        for argument in node.args:
            visit(argument, owner, line, local_bindings)
        if not isinstance(node.callee, NameExpr):
            visit(node.callee, owner, line, local_bindings)
            return

        name = node.callee.name
        external = externs.get(name)
        if external is not None:
            site = plan.resolve_site(owner, render_expr(node), source_line=line)
            if site is None:
                return
            specialized = _substitute(node, local_bindings)
            resolved.append(
                ResolvedHostInvocation(
                    invocation_id=site.id,
                    effect=site.effect,
                    call=render_expr(specialized),
                    failure_type=site.failure_type,
                )
            )
            return

        nested = functions.get(name)
        if (
            nested is None
            or nested.guards
            or nested.expression is None
            or nested.name in visited
            or len(nested.params) != len(node.args)
        ):
            return
        nested_bindings = {
            parameter.name: _substitute(argument, local_bindings)
            for parameter, argument in zip(nested.params, node.args, strict=True)
        }
        visit(
            nested.expression,
            nested.name,
            nested.line,
            nested_bindings,
        )

    visit(expression, caller, source_line, environment)
    unique: list[ResolvedHostInvocation] = []
    seen: set[tuple[str, str]] = set()
    for invocation in resolved:
        key = (invocation.invocation_id, invocation.call)
        if key not in seen:
            seen.add(key)
            unique.append(invocation)
    return tuple(unique)

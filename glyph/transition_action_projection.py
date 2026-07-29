from __future__ import annotations

from copy import deepcopy
from typing import Mapping, Sequence

from ._transition_branch_semantics import (
    branch_value_for_transition,
    build_machine_branch_context,
    field_index,
    unwrap_expr,
)
from .artifacts import CompilationModel
from .compiler import (
    AliasDecl,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    NameExpr,
    SumDecl,
    TypeRef,
)
from .execution_ir import render_expr
from .state_transition_ir import _actions_in_expr, _render_type


_ACTION_PROVENANCE = "transition-operation-invocation"
_OUTPUT_PROVENANCE = "machine-output-projection"
_EFFECT_PROVENANCE = "declared-effect-invocation"


def _project_constructor_field(
    expression: Expr,
    *,
    state_decl: object,
    field_position: int,
    state_param: str,
) -> Expr | None:
    value = unwrap_expr(expression)
    if isinstance(value, NameExpr) and value.name == state_param:
        return None
    if not (
        isinstance(value, CallExpr)
        and isinstance(value.callee, NameExpr)
        and value.callee.name == state_decl.name
        and len(value.args) == len(state_decl.fields)
    ):
        return None
    return value.args[field_position]


def _variant_parts(
    expression: Expr,
    declaration: SumDecl,
) -> tuple[str | None, tuple[Expr, ...]]:
    variants = {item.name for item in declaration.variants}
    value = unwrap_expr(expression)
    if isinstance(value, NameExpr) and value.name in variants:
        return value.name, ()
    if (
        isinstance(value, CallExpr)
        and isinstance(value.callee, NameExpr)
        and value.callee.name in variants
    ):
        return value.callee.name, value.args
    return None, ()


def _output_value(
    expression: Expr | None,
    *,
    output_type: TypeRef,
    output_sum: SumDecl,
    source: Mapping[str, object],
) -> dict[str, object] | None:
    if expression is None:
        return None
    variant, payload = _variant_parts(expression, output_sum)
    if variant is None:
        return None
    rendered = render_expr(expression)
    return {
        "display": rendered,
        "expression": rendered,
        "type": _render_type(output_type),
        "variant": variant,
        "payload": [render_expr(item) for item in payload],
        "provenance": _OUTPUT_PROVENANCE,
        "source": dict(source),
    }


def _operation_name(call: str) -> str:
    open_position = call.find("(")
    return call[:open_position] if open_position > 0 else call


def _effect_values(
    branch_value: Expr | None,
    *,
    legacy_action: object,
    synthesized_failure: bool,
    functions: Mapping[str, object],
    externs: Mapping[str, ExternDecl],
    aliases: Mapping[str, TypeRef],
    source: Mapping[str, object],
) -> list[dict[str, object]]:
    effects = (
        _actions_in_expr(
            branch_value,
            functions=functions,
            externs=externs,
            aliases=aliases,
        )
        if branch_value is not None
        else ()
    )
    legacy = str(legacy_action or "").strip()
    if synthesized_failure and legacy:
        effects = tuple(item for item in effects if item.call == legacy)
    if not effects and legacy:
        effects = tuple(
            type("LegacyEffect", (), {"call": item, "failure_type": None})()
            for item in legacy.split("; ")
            if item
        )
    return [
        {
            "operation": _operation_name(item.call),
            "expression": item.call,
            "failure_type": item.failure_type,
            "sequence": index,
            "effectful": True,
            "kind": "effect-invocation",
            "provenance": _EFFECT_PROVENANCE,
            "source": dict(source),
        }
        for index, item in enumerate(effects, start=1)
    ]


def _operation_action(
    invocations: Sequence[Mapping[str, object]],
    *,
    source: Mapping[str, object],
) -> dict[str, object] | None:
    expressions = [
        str(item.get("expression") or "").strip()
        for item in invocations
        if str(item.get("expression") or "").strip()
    ]
    if not expressions:
        return None
    operations = [
        str(item.get("operation") or "").strip()
        for item in invocations
        if str(item.get("operation") or "").strip()
    ]
    display = "; ".join(expressions)
    return {
        "display": display,
        "expression": display,
        "operation": operations[0] if len(operations) == 1 else None,
        "operations": operations,
        "kind": (
            "operation-invocation"
            if len(expressions) == 1
            else "operation-sequence"
        ),
        "effectful": True,
        "provenance": _ACTION_PROVENANCE,
        "source": dict(source),
    }


def _diagnostic(code: str, message: str, line: int) -> dict[str, object]:
    return {
        "severity": "warning",
        "code": code,
        "message": message,
        "line": line,
    }


def project_machine_transition_actions(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Derive edge Actions from proven operation invocations only."""

    result = deepcopy(machine_view)
    context = build_machine_branch_context(model, str(result.get("name") or ""))
    if context is None:
        return result

    externs = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, ExternDecl)
    }
    aliases = {
        item.name: item.target
        for item in model.program.declarations
        if isinstance(item, AliasDecl)
    }
    machine = context.machine
    state_decl = context.state_decl
    state_names = [str(item.get("name", "")) for item in result.get("states", [])]
    unreachable_lines = frozenset(map(int, result.get("unreachable_branches", [])))

    output_selector = (
        machine.action_selector
        if isinstance(machine.action_selector, FieldExpr)
        else None
    )
    output_index = field_index(state_decl, output_selector)
    output_type = state_decl.fields[output_index].ty if output_index is not None else None
    output_sum = context.sums.get(output_type.name) if output_type is not None else None

    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
    generated: list[dict[str, object]] = []
    transitions: list[dict[str, object]] = []
    for original in result.get("transitions", []):
        transition = dict(original)
        branch_value = branch_value_for_transition(
            context,
            transition,
            state_names,
            unreachable_lines=unreachable_lines,
        )
        source = transition.get("source", {})
        source_map = (
            dict(source)
            if isinstance(source, Mapping)
            else {"line": 1, "column": 1}
        )
        effect_invocations = _effect_values(
            branch_value,
            legacy_action=transition.get("action"),
            synthesized_failure=bool(transition.get("synthesized_failure")),
            functions=context.functions,
            externs=externs,
            aliases=aliases,
            source=source_map,
        )
        transition["effect_invocations"] = effect_invocations
        transition["action_invocations"] = [dict(item) for item in effect_invocations]
        transition["action"] = _operation_action(
            effect_invocations,
            source=source_map,
        )

        projected_expression = (
            _project_constructor_field(
                branch_value,
                state_decl=state_decl,
                field_position=output_index,
                state_param=machine.state_param.name,
            )
            if branch_value is not None and output_index is not None
            else None
        )
        emitted_output = (
            _output_value(
                projected_expression,
                output_type=output_type,
                output_sum=output_sum,
                source=source_map,
            )
            if output_type is not None and output_sum is not None
            else None
        )
        transition["emitted_output"] = emitted_output

        if (
            output_selector is not None
            and projected_expression is not None
            and emitted_output is None
        ):
            generated.append(
                _diagnostic(
                    "STIR_OUTPUT_UNRESOLVED",
                    (
                        f"transition output `{render_expr(projected_expression)}` could not be "
                        f"resolved as a variant of `{_render_type(output_type)}`"
                    ),
                    int(source_map.get("line", 1)),
                )
            )
        transitions.append(transition)

    seen = {
        (item.get("code"), item.get("line"), item.get("message"))
        for item in diagnostics
    }
    for item in generated:
        key = (item.get("code"), item.get("line"), item.get("message"))
        if key not in seen:
            diagnostics.append(item)
            seen.add(key)

    projection_metadata = (
        None
        if output_selector is None
        else {
            "expression": render_expr(output_selector),
            "field": output_selector.field,
            "type": _render_type(output_type),
            "semantic_role": "emitted-output",
            "legacy_source_spelling": "action=",
        }
    )
    analysis = dict(result.get("analysis", {}))
    analysis.update(
        {
            "projected_action_count": sum(
                1 for item in transitions if item.get("action") is not None
            ),
            "operation_action_count": sum(
                len(item.get("action_invocations", [])) for item in transitions
            ),
            "effect_invocation_count": sum(
                len(item.get("effect_invocations", [])) for item in transitions
            ),
            "emitted_output_count": sum(
                1 for item in transitions if item.get("emitted_output") is not None
            ),
            "state_field_action_count": 0,
            "action_projection_declared": output_selector is not None,
            "output_projection_declared": output_selector is not None,
        }
    )
    result.update(
        {
            "transitions": transitions,
            "diagnostics": diagnostics,
            "analysis": analysis,
            "action_projection": projection_metadata,
            "output_projection": projection_metadata,
        }
    )
    return result


__all__ = ["project_machine_transition_actions"]

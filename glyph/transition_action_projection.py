from __future__ import annotations

from copy import deepcopy
from typing import Mapping, Sequence

from .artifacts import CompilationModel
from .compiler import (
    AliasDecl,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    NameExpr,
    ProductDecl,
    SumDecl,
    TryExpr,
    TypeRef,
    parse_expr,
)
from .execution_ir import render_expr
from .state_transition_compiler import _root_branches
from .state_transition_ir import _actions_in_expr, _render_type


ACTION_PROVENANCE = "transition-operation-invocation"
OUTPUT_PROVENANCE = "machine-output-projection"
EFFECT_PROVENANCE = "declared-effect-invocation"


def _unwrap(expr: Expr) -> Expr:
    if isinstance(expr, TryExpr):
        return _unwrap(expr.expr)
    if (
        isinstance(expr, CallExpr)
        and isinstance(expr.callee, NameExpr)
        and expr.callee.name == "Ok"
        and len(expr.args) == 1
    ):
        return _unwrap(expr.args[0])
    return expr


def _field_index(state_decl: ProductDecl, selector: FieldExpr | None) -> int | None:
    if selector is None:
        return None
    return next(
        (
            index
            for index, field in enumerate(state_decl.fields)
            if field.name == selector.field
        ),
        None,
    )


def _project_constructor_field(
    expr: Expr,
    *,
    state_decl: ProductDecl,
    field_index: int,
    state_param: str,
) -> Expr | None:
    value = _unwrap(expr)
    if isinstance(value, NameExpr) and value.name == state_param:
        return None
    if not (
        isinstance(value, CallExpr)
        and isinstance(value.callee, NameExpr)
        and value.callee.name == state_decl.name
        and len(value.args) == len(state_decl.fields)
    ):
        return None
    return value.args[field_index]


def _variant_parts(
    expr: Expr,
    declaration: SumDecl,
) -> tuple[str | None, tuple[Expr, ...]]:
    variants = {item.name for item in declaration.variants}
    value = _unwrap(expr)
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
    expr: Expr | None,
    *,
    output_type: TypeRef,
    output_sum: SumDecl,
    source: Mapping[str, object],
) -> dict[str, object] | None:
    if expr is None:
        return None
    variant, payload = _variant_parts(expr, output_sum)
    if variant is None:
        return None
    rendered = render_expr(expr)
    return {
        "display": rendered,
        "expression": rendered,
        "type": _render_type(output_type),
        "variant": variant,
        "payload": [render_expr(item) for item in payload],
        "provenance": OUTPUT_PROVENANCE,
        "source": dict(source),
    }


def _operation_name(call: str) -> str:
    open_pos = call.find("(")
    return call[:open_pos] if open_pos > 0 else call


def _effect_values(
    branch_value: Expr | None,
    *,
    legacy_action: object,
    synthesized_failure: bool,
    functions: Mapping[str, FunctionDecl],
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
            "provenance": EFFECT_PROVENANCE,
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
        "provenance": ACTION_PROVENANCE,
        "source": dict(source),
    }


def _branch_for_transition(
    branches: Sequence[object],
    transition: Mapping[str, object],
) -> object | None:
    source = transition.get("source", {})
    line = int(source.get("line", 0)) if isinstance(source, Mapping) else 0
    source_state = str(transition.get("source_state", ""))
    target_state = str(transition.get("target_state", ""))
    synthesized = bool(transition.get("synthesized_failure"))
    candidates = [item for item in branches if int(getattr(item, "line", 0)) == line]
    if synthesized:
        return candidates[0] if candidates else None
    for item in candidates:
        target = getattr(item, "target", "")
        resolved = source_state if target == "__same__" else str(target)
        if resolved == target_state:
            return item
    return candidates[0] if len(candidates) == 1 else None


def _conditional_block_values(
    model: CompilationModel,
    function_name: str | None,
) -> tuple[tuple[int, str, Expr], ...]:
    if function_name is None:
        return ()
    block = next((item for item in model.blocks if item.name == function_name), None)
    if block is None:
        return ()
    values: list[tuple[int, str, Expr]] = []
    for binding in block.bindings:
        if binding.kind != "conditional":
            continue
        for offset, original in enumerate(binding.source.splitlines(), start=1):
            stripped = original.strip()
            arrow = stripped.find("=>")
            if arrow < 0:
                continue
            condition_text = stripped[:arrow].strip()
            value_text = stripped[arrow + 2 :].strip()
            if not value_text:
                continue
            try:
                value = parse_expr(value_text)
                condition = (
                    "otherwise"
                    if condition_text == "_"
                    else render_expr(parse_expr(condition_text))
                )
            except Exception:
                continue
            values.append((binding.line + offset, condition, value))
    return tuple(values)


def _block_value_for_transition(
    values: Sequence[tuple[int, str, Expr]],
    transition: Mapping[str, object],
) -> Expr | None:
    source = transition.get("source", {})
    line = int(source.get("line", 0)) if isinstance(source, Mapping) else 0
    raw = str(transition.get("condition_raw") or transition.get("condition") or "")
    condition = "otherwise" if raw in {"", "otherwise", "next"} else raw
    exact = [
        value
        for candidate_line, candidate_condition, value in values
        if candidate_line == line and candidate_condition == condition
    ]
    if exact:
        return exact[0]
    matching = [
        value
        for _, candidate_condition, value in values
        if candidate_condition == condition
    ]
    return matching[0] if len(matching) == 1 else None


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
    """Derive edge Actions from executed operations, never from state values.

    The legacy ``machine action=state.field`` selector is retained as an
    Emitted Output projection for decision provenance and compatibility.
    Target State and Emitted Output are never Action fallbacks.
    """

    result = deepcopy(machine_view)
    machine = next(
        (item for item in model.machines if item.name == result.get("name")),
        None,
    )
    if machine is None or not isinstance(machine.selector, FieldExpr):
        return result

    products = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, ProductDecl)
    }
    sums = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, SumDecl)
    }
    functions = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, FunctionDecl)
    }
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
    state_decl = products.get(machine.state_param.ty.name)
    if state_decl is None:
        return result
    selector_index = _field_index(state_decl, machine.selector)
    if selector_index is None:
        return result
    selector_sum = sums.get(state_decl.fields[selector_index].ty.name)
    if selector_sum is None:
        return result

    output_selector = (
        machine.action_selector
        if isinstance(machine.action_selector, FieldExpr)
        else None
    )
    output_index = _field_index(state_decl, output_selector)
    output_type = state_decl.fields[output_index].ty if output_index is not None else None
    output_sum = sums.get(output_type.name) if output_type is not None else None

    next_call = machine.next_expr if isinstance(machine.next_expr, CallExpr) else None
    next_name = (
        next_call.callee.name
        if next_call is not None and isinstance(next_call.callee, NameExpr)
        else None
    )
    branches = (
        _root_branches(
            next_name,
            functions=functions,
            state_decl=state_decl,
            selector_index=selector_index,
            variants={item.name for item in selector_sum.variants},
            root_state_param=machine.state_param.name,
        )
        if next_name is not None
        else ()
    )
    block_values = _conditional_block_values(model, next_name)

    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
    generated: list[dict[str, object]] = []
    transitions: list[dict[str, object]] = []
    for original in result.get("transitions", []):
        transition = dict(original)
        branch = _branch_for_transition(branches, transition)
        branch_value = getattr(branch, "value", None) if branch is not None else None
        if branch_value is None:
            branch_value = _block_value_for_transition(block_values, transition)
        source = transition.get("source", {})
        source_map = (
            dict(source)
            if isinstance(source, Mapping)
            else {"line": 1, "column": 1}
        )
        legacy_action = transition.get("action")
        effect_invocations = _effect_values(
            branch_value,
            legacy_action=legacy_action,
            synthesized_failure=bool(transition.get("synthesized_failure")),
            functions=functions,
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

        projected_expr = (
            _project_constructor_field(
                branch_value,
                state_decl=state_decl,
                field_index=output_index,
                state_param=machine.state_param.name,
            )
            if branch_value is not None and output_index is not None
            else None
        )
        emitted_output = (
            _output_value(
                projected_expr,
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
            and branch_value is not None
            and projected_expr is not None
            and emitted_output is None
        ):
            line = int(source_map.get("line", 1))
            generated.append(
                _diagnostic(
                    "STIR_OUTPUT_UNRESOLVED",
                    (
                        f"transition output `{render_expr(projected_expr)}` could not be "
                        f"resolved as a variant of `{_render_type(output_type)}`"
                    ),
                    line,
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


__all__ = [
    "ACTION_PROVENANCE",
    "EFFECT_PROVENANCE",
    "OUTPUT_PROVENANCE",
    "project_machine_transition_actions",
]

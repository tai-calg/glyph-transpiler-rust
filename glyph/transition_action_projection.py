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
)
from .execution_ir import render_expr
from .state_transition_compiler import _root_branches
from .state_transition_ir import _actions_in_expr, _render_type


ACTION_PROVENANCE = "machine-action-projection"


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


def _action_value(
    expr: Expr | None,
    *,
    action_type: TypeRef,
    action_sum: SumDecl,
    source: Mapping[str, object],
) -> dict[str, object] | None:
    if expr is None:
        return None
    variant, payload = _variant_parts(expr, action_sum)
    if variant is None:
        return None
    rendered = render_expr(expr)
    return {
        "display": rendered,
        "expression": rendered,
        "type": _render_type(action_type),
        "variant": variant,
        "payload": [render_expr(item) for item in payload],
        "provenance": ACTION_PROVENANCE,
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
            "source": dict(source),
        }
        for index, item in enumerate(effects, start=1)
    ]


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


def _warning(message: str, line: int) -> dict[str, object]:
    return {
        "severity": "warning",
        "code": "STIR_ACTION_UNRESOLVED",
        "message": message,
        "line": line,
    }


def project_machine_transition_actions(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
    """Separate projected transition Actions from Effect invocations.

    Action is derived only from the optional ``machine action=state.field`` projection.
    Existing compiler ``action`` strings are external Effect calls and are moved to
    ``effect_invocations``. Target state is never used as an Action fallback.
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

    action_selector = (
        machine.action_selector
        if isinstance(machine.action_selector, FieldExpr)
        else None
    )
    action_index = _field_index(state_decl, action_selector)
    action_type = state_decl.fields[action_index].ty if action_index is not None else None
    action_sum = sums.get(action_type.name) if action_type is not None else None

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

    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
    generated: list[dict[str, object]] = []
    transitions: list[dict[str, object]] = []
    for original in result.get("transitions", []):
        transition = dict(original)
        branch = _branch_for_transition(branches, transition)
        branch_value = getattr(branch, "value", None) if branch is not None else None
        source = transition.get("source", {})
        source_map = dict(source) if isinstance(source, Mapping) else {"line": 1, "column": 1}
        legacy_action = transition.get("action")
        transition["effect_invocations"] = _effect_values(
            branch_value,
            legacy_action=legacy_action,
            synthesized_failure=bool(transition.get("synthesized_failure")),
            functions=functions,
            externs=externs,
            aliases=aliases,
            source=source_map,
        )

        projected_expr = (
            _project_constructor_field(
                branch_value,
                state_decl=state_decl,
                field_index=action_index,
                state_param=machine.state_param.name,
            )
            if branch_value is not None and action_index is not None
            else None
        )
        action = (
            _action_value(
                projected_expr,
                action_type=action_type,
                action_sum=action_sum,
                source=source_map,
            )
            if action_type is not None and action_sum is not None
            else None
        )
        transition["action"] = action

        if (
            action_selector is not None
            and branch_value is not None
            and projected_expr is not None
            and action is None
        ):
            line = int(source_map.get("line", 1))
            generated.append(
                _warning(
                    (
                        f"transition Action `{render_expr(projected_expr)}` could not be "
                        f"resolved as a variant of `{_render_type(action_type)}`"
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

    analysis = dict(result.get("analysis", {}))
    analysis.update(
        {
            "projected_action_count": sum(
                1 for item in transitions if item.get("action") is not None
            ),
            "effect_invocation_count": sum(
                len(item.get("effect_invocations", [])) for item in transitions
            ),
            "action_projection_declared": action_selector is not None,
        }
    )
    result.update(
        {
            "transitions": transitions,
            "diagnostics": diagnostics,
            "analysis": analysis,
            "action_projection": (
                None
                if action_selector is None
                else {
                    "expression": render_expr(action_selector),
                    "field": action_selector.field,
                    "type": _render_type(action_type),
                }
            ),
        }
    )
    return result


__all__ = ["ACTION_PROVENANCE", "project_machine_transition_actions"]

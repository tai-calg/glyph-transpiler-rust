from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping, Sequence

from .artifacts import CompilationModel
from .compiler import (
    AliasDecl,
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    NameExpr,
    NumberExpr,
    ProductDecl,
    SumDecl,
    TypeRef,
    UnaryExpr,
    parse_expr,
)
from .execution_ir import render_expr
from .machine import MachineDecl
from .state_transition_contract import (
    STATE_TRANSITION_IR_SCHEMA,
    STATE_TRANSITION_IR_VERSION,
)


_ROLE_CONFIRMED = "confirmed-trigger"
_ROLE_INFERRED = "inferred-trigger"
_ROLE_PROVISIONAL = "provisional-trigger"
_CONFIDENCE_EXACT = "exact"
_CONFIDENCE_INFERRED = "dataflow-inferred"
_CONFIDENCE_FALLBACK = "fallback"


@dataclass(frozen=True)
class _Context:
    state_param: str
    selector_field: str
    source_state: str
    input_names: frozenset[str]
    locals: Mapping[str, TypeRef]
    definitions: Mapping[str, Expr]
    products: Mapping[str, ProductDecl]
    sums: Mapping[str, SumDecl]
    functions: Mapping[str, FunctionDecl]
    externs: Mapping[str, ExternDecl]
    aliases: Mapping[str, TypeRef]


@dataclass(frozen=True)
class _Facts:
    roots: frozenset[str]
    value_type: TypeRef | None
    path: tuple[str, ...]

    @property
    def input_derived(self) -> bool:
        return any(
            root.startswith("input:") or root.startswith("external:")
            for root in self.roots
        )

    @property
    def state_derived(self) -> bool:
        return "state" in self.roots

    @property
    def unknown(self) -> bool:
        return any(root.startswith("unknown:") for root in self.roots)


def _resolve_alias(
    ty: TypeRef | None,
    aliases: Mapping[str, TypeRef],
) -> TypeRef | None:
    current = ty
    seen: set[str] = set()
    while (
        current is not None
        and not current.args
        and current.name in aliases
        and current.name not in seen
    ):
        seen.add(current.name)
        current = aliases[current.name]
    return current


def _expr_type(
    expr: Expr,
    context: _Context,
    visited: frozenset[str] = frozenset(),
) -> TypeRef | None:
    if isinstance(expr, BoolExpr):
        return TypeRef("bool")
    if isinstance(expr, NumberExpr):
        return TypeRef("f32" if "." in expr.value else "i32")
    if isinstance(expr, NameExpr):
        if expr.name in context.locals:
            return _resolve_alias(context.locals[expr.name], context.aliases)
        if expr.name in context.definitions and expr.name not in visited:
            return _expr_type(
                context.definitions[expr.name],
                context,
                visited | {expr.name},
            )
        return None
    if isinstance(expr, FieldExpr):
        base_type = _expr_type(expr.base, context, visited)
        if base_type is None:
            return None
        product = context.products.get(base_type.name)
        if product is None:
            return None
        field = next(
            (item for item in product.fields if item.name == expr.field),
            None,
        )
        return None if field is None else _resolve_alias(field.ty, context.aliases)
    if isinstance(expr, UnaryExpr):
        if expr.op == "!":
            return TypeRef("bool")
        return _expr_type(expr.expr, context, visited)
    if isinstance(expr, BinaryExpr):
        if expr.op in {"&", "|", "==", "!=", "<", ">", "<=", ">="}:
            return TypeRef("bool")
        return _expr_type(expr.left, context, visited) or _expr_type(
            expr.right,
            context,
            visited,
        )
    if isinstance(expr, CallExpr) and isinstance(expr.callee, NameExpr):
        declaration = context.functions.get(expr.callee.name)
        if declaration is not None:
            return _resolve_alias(declaration.return_type, context.aliases)
        external = context.externs.get(expr.callee.name)
        if external is not None:
            return _resolve_alias(external.return_type, context.aliases)
        if expr.callee.name in context.products:
            return TypeRef(expr.callee.name)
        for sum_name, declaration in context.sums.items():
            if expr.callee.name in {
                variant.name for variant in declaration.variants
            }:
                return TypeRef(sum_name)
    return None


def _facts(
    expr: Expr,
    context: _Context,
    visited: frozenset[str] = frozenset(),
) -> _Facts:
    if isinstance(expr, NameExpr):
        if expr.name == context.state_param:
            return _Facts(
                frozenset({"state"}),
                _expr_type(expr, context),
                (expr.name,),
            )
        if expr.name in context.input_names:
            return _Facts(
                frozenset({f"input:{expr.name}"}),
                _expr_type(expr, context),
                (expr.name,),
            )
        if expr.name in context.definitions and expr.name not in visited:
            nested = _facts(
                context.definitions[expr.name],
                context,
                visited | {expr.name},
            )
            return _Facts(
                nested.roots,
                _expr_type(expr, context, visited),
                (*nested.path, expr.name),
            )
        if expr.name in context.locals:
            return _Facts(
                frozenset({f"unknown:{expr.name}"}),
                _expr_type(expr, context),
                (expr.name,),
            )
        if any(
            expr.name in {variant.name for variant in declaration.variants}
            for declaration in context.sums.values()
        ):
            return _Facts(frozenset(), _expr_type(expr, context), (expr.name,))
        return _Facts(
            frozenset({f"unknown:{expr.name}"}),
            None,
            (expr.name,),
        )
    if isinstance(expr, FieldExpr):
        nested = _facts(expr.base, context, visited)
        return _Facts(
            nested.roots,
            _expr_type(expr, context, visited),
            (*nested.path, render_expr(expr)),
        )
    if isinstance(expr, UnaryExpr):
        nested = _facts(expr.expr, context, visited)
        return _Facts(
            nested.roots,
            _expr_type(expr, context, visited),
            nested.path,
        )
    if isinstance(expr, BinaryExpr):
        left = _facts(expr.left, context, visited)
        right = _facts(expr.right, context, visited)
        return _Facts(
            left.roots | right.roots,
            _expr_type(expr, context, visited),
            (*left.path, *right.path),
        )
    if isinstance(expr, CallExpr):
        roots: frozenset[str] = frozenset()
        path: tuple[str, ...] = ()
        for argument in expr.args:
            item = _facts(argument, context, visited)
            roots |= item.roots
            path = (*path, *item.path)
        if isinstance(expr.callee, NameExpr):
            name = expr.callee.name
            if name in context.externs and not expr.args:
                roots |= {f"external:{name}"}
            path = (*path, f"{name}(...)")
        return _Facts(roots, _expr_type(expr, context, visited), path)
    return _Facts(
        frozenset(),
        _expr_type(expr, context, visited),
        (render_expr(expr),),
    )


def _flatten_and(expr: Expr) -> list[Expr]:
    if isinstance(expr, BinaryExpr) and expr.op == "&":
        return [*_flatten_and(expr.left), *_flatten_and(expr.right)]
    return [expr]


def _combine_and(parts: Sequence[Expr]) -> Expr | None:
    iterator = iter(parts)
    try:
        result = next(iterator)
    except StopIteration:
        return None
    for part in iterator:
        result = BinaryExpr("&", result, part)
    return result


def _variant_name(expr: Expr) -> str | None:
    if isinstance(expr, NameExpr):
        return expr.name
    if isinstance(expr, CallExpr) and isinstance(expr.callee, NameExpr):
        return expr.callee.name
    return None


def _is_source_state(expr: Expr, context: _Context) -> bool:
    if not isinstance(expr, BinaryExpr) or expr.op != "==":
        return False
    for left, right in ((expr.left, expr.right), (expr.right, expr.left)):
        if (
            isinstance(left, FieldExpr)
            and isinstance(left.base, NameExpr)
            and left.base.name == context.state_param
            and left.field == context.selector_field
            and isinstance(right, NameExpr)
            and right.name == context.source_state
        ):
            return True
    return False


def _direct_input_subject(expr: Expr, context: _Context) -> bool:
    if isinstance(expr, NameExpr):
        return expr.name in context.input_names and expr.name not in context.definitions
    if isinstance(expr, FieldExpr):
        base = expr.base
        return isinstance(base, NameExpr) and base.name in context.input_names
    return False


def _trigger_atom(expr: Expr, context: _Context) -> dict[str, object] | None:
    if not isinstance(expr, BinaryExpr) or expr.op != "==":
        return None
    for subject, pattern in ((expr.left, expr.right), (expr.right, expr.left)):
        value_type = _expr_type(subject, context)
        variant = _variant_name(pattern)
        if value_type is None or variant is None:
            continue
        declaration = context.sums.get(value_type.name)
        if declaration is None or variant not in {
            item.name for item in declaration.variants
        }:
            continue
        facts = _facts(subject, context)
        if not facts.input_derived:
            continue
        if facts.state_derived or facts.unknown:
            return {
                "display": variant,
                "expression": render_expr(expr),
                "role": _ROLE_PROVISIONAL,
                "confidence": _CONFIDENCE_FALLBACK,
                "value_type": value_type.name,
                "variant": variant,
                "provenance_roots": sorted(facts.roots),
                "dataflow_path": list(dict.fromkeys(facts.path)),
            }
        direct = _direct_input_subject(subject, context)
        return {
            "display": variant,
            "expression": render_expr(expr),
            "role": _ROLE_CONFIRMED if direct else _ROLE_INFERRED,
            "confidence": _CONFIDENCE_EXACT if direct else _CONFIDENCE_INFERRED,
            "value_type": value_type.name,
            "variant": variant,
            "provenance_roots": sorted(facts.roots),
            "dataflow_path": list(dict.fromkeys(facts.path)),
        }
    return None


def _warning(code: str, message: str, line: int) -> dict[str, object]:
    return {
        "severity": "warning",
        "code": code,
        "message": message,
        "line": line,
    }


def _classification(
    condition: Expr | None,
    *,
    context: _Context,
    line: int,
) -> dict[str, object]:
    if condition is None:
        return {
            "trigger": None,
            "guards": [],
            "unclassified_conditions": [],
            "diagnostics": [],
        }

    atoms = [
        part
        for part in _flatten_and(condition)
        if not _is_source_state(part, context)
    ]
    trigger_atoms: list[tuple[Expr, dict[str, object]]] = []
    remaining: list[Expr] = []
    for atom in atoms:
        trigger = _trigger_atom(atom, context)
        if trigger is None:
            remaining.append(atom)
        else:
            trigger_atoms.append((atom, trigger))

    diagnostics: list[dict[str, object]] = []
    guards: list[str] = []
    unclassified: list[str] = []
    trigger: dict[str, object] | None = None

    if len(trigger_atoms) == 1:
        trigger = trigger_atoms[0][1]
        if trigger["role"] == _ROLE_PROVISIONAL:
            diagnostics.append(
                _warning(
                    "STIR_MIXED_TRIGGER_GUARD_PREDICATE",
                    (
                        f"`{trigger['expression']}` is input-derived but also depends on "
                        "state or unresolved values. It is rendered provisionally as a trigger."
                    ),
                    line,
                )
            )
        for atom in remaining:
            facts = _facts(atom, context)
            if facts.unknown and not (
                facts.input_derived or facts.state_derived
            ):
                unclassified.append(render_expr(atom))
                diagnostics.append(
                    _warning(
                        "STIR_CONDITION_PROVENANCE_UNKNOWN",
                        (
                            f"`{render_expr(atom)}` could not be classified because its "
                            "type or data origin is unknown."
                        ),
                        line,
                    )
                )
            else:
                guards.append(render_expr(atom))
    elif len(trigger_atoms) > 1:
        all_parts = [item[0] for item in trigger_atoms]
        expression = _combine_and(all_parts)
        assert expression is not None
        facts = _facts(expression, context)
        trigger = {
            "display": render_expr(expression),
            "expression": render_expr(expression),
            "role": _ROLE_PROVISIONAL,
            "confidence": _CONFIDENCE_FALLBACK,
            "value_type": None,
            "variant": None,
            "provenance_roots": sorted(facts.roots),
            "dataflow_path": list(dict.fromkeys(facts.path)),
        }
        diagnostics.append(
            _warning(
                "STIR_MULTIPLE_CONFIRMED_TRIGGERS",
                (
                    "The transition contains multiple event discriminators. They are "
                    "rendered together as one provisional trigger."
                ),
                line,
            )
        )
        for atom in remaining:
            guards.append(render_expr(atom))
    else:
        input_parts: list[Expr] = []
        for atom in remaining:
            facts = _facts(atom, context)
            if facts.input_derived:
                input_parts.append(atom)
            elif facts.state_derived or not facts.roots:
                guards.append(render_expr(atom))
            else:
                unclassified.append(render_expr(atom))
                diagnostics.append(
                    _warning(
                        "STIR_CONDITION_PROVENANCE_UNKNOWN",
                        (
                            f"`{render_expr(atom)}` could not be classified because its "
                            "type or data origin is unknown."
                        ),
                        line,
                    )
                )
        if input_parts:
            expression = _combine_and(input_parts)
            assert expression is not None
            facts = _facts(expression, context)
            trigger = {
                "display": render_expr(expression),
                "expression": render_expr(expression),
                "role": _ROLE_PROVISIONAL,
                "confidence": _CONFIDENCE_FALLBACK,
                "value_type": None,
                "variant": None,
                "provenance_roots": sorted(facts.roots),
                "dataflow_path": list(dict.fromkeys(facts.path)),
            }
            code = (
                "STIR_MULTIPLE_TRIGGER_CANDIDATES"
                if len(input_parts) > 1
                else "STIR_TRIGGER_AMBIGUOUS_FALLBACK"
            )
            message = (
                "The transition contains multiple input-derived conditions and no "
                "confirmed event discriminator. They are rendered as one provisional trigger."
                if len(input_parts) > 1
                else (
                    f"`{render_expr(expression)}` is input-derived, but the compiler "
                    "cannot determine whether it represents an occurrence or a persistent "
                    "condition. It is rendered provisionally as a trigger."
                )
            )
            diagnostics.append(_warning(code, message, line))

    return {
        "trigger": trigger,
        "guards": guards,
        "unclassified_conditions": unclassified,
        "diagnostics": diagnostics,
    }


def _action_display(action: object) -> str:
    if isinstance(action, Mapping):
        return str(action.get("display") or action.get("expression") or "")
    return "" if action is None else str(action)


def _display_label(
    trigger: Mapping[str, object] | None,
    guards: Sequence[str],
    action: object,
    failure_type: str | None,
    unclassified: Sequence[str],
) -> str:
    label = ""
    action_text = _action_display(action)
    if trigger is not None:
        prefix = "? " if trigger.get("role") == _ROLE_PROVISIONAL else ""
        label = prefix + str(trigger.get("display", ""))
    if guards:
        guard_text = "&".join(guards)
        label += f" [{guard_text}]" if label else f"[{guard_text}]"
    if unclassified:
        unknown = "&".join(unclassified)
        label += f" ? {unknown}" if label else f"? {unknown}"
    if action_text:
        label += f" / {action_text}" if label else f"/ {action_text}"
    if failure_type:
        label += f" | {failure_type}"
    return label


def _matching_clause(
    functions: Mapping[str, FunctionDecl],
    line: int,
    raw: str,
) -> FunctionDecl | None:
    matches: list[FunctionDecl] = []
    for declaration in functions.values():
        for clause in declaration.guards:
            rendered = (
                "otherwise"
                if clause.condition is None
                else render_expr(clause.condition)
            )
            if clause.line == line and rendered == raw:
                matches.append(declaration)
    return matches[0] if len(matches) == 1 else None


def _block_definitions(
    model: CompilationModel,
    declaration_name: str | None,
) -> dict[str, Expr]:
    if declaration_name is None:
        return {}
    for block in model.blocks:
        helper_names = {
            block.final_helper,
            *block.continuation_helpers,
            *(binding.value_helper for binding in block.bindings),
        }
        if declaration_name not in helper_names:
            continue
        definitions: dict[str, Expr] = {}
        for binding in block.bindings:
            if binding.kind != "expression":
                continue
            try:
                definitions[binding.name] = parse_expr(binding.source)
            except Exception:
                continue
        return definitions
    return {}


def _context(
    model: CompilationModel,
    machine: MachineDecl,
    transition: Mapping[str, object],
    *,
    products: Mapping[str, ProductDecl],
    sums: Mapping[str, SumDecl],
    functions: Mapping[str, FunctionDecl],
    externs: Mapping[str, ExternDecl],
    aliases: Mapping[str, TypeRef],
) -> _Context:
    line = int(transition.get("source", {}).get("line", 1))
    raw = str(
        transition.get("condition_raw")
        or transition.get("condition")
        or ""
    )
    declaration = _matching_clause(functions, line, raw)
    locals_: dict[str, TypeRef] = {
        parameter.name: parameter.ty for parameter in machine.params
    }
    if declaration is not None:
        locals_.update(
            {parameter.name: parameter.ty for parameter in declaration.params}
        )
    return _Context(
        state_param=machine.state_param.name,
        selector_field=(
            machine.selector.field
            if isinstance(machine.selector, FieldExpr)
            else ""
        ),
        source_state=str(transition.get("source_state", "")),
        input_names=frozenset(
            parameter.name
            for parameter in machine.params
            if parameter.name != machine.state_param.name
        ),
        locals=locals_,
        definitions=_block_definitions(
            model,
            None if declaration is None else declaration.name,
        ),
        products=products,
        sums=sums,
        functions=functions,
        externs=externs,
        aliases=aliases,
    )


def classify_machine_transition_roles(
    model: CompilationModel,
    machine_view: dict[str, object],
) -> dict[str, object]:
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

    transitions: list[dict[str, object]] = []
    generated_diagnostics: list[dict[str, object]] = []
    for original in result.get("transitions", []):
        transition = dict(original)
        raw = str(
            transition.get("condition_raw")
            or transition.get("condition")
            or ""
        )
        condition: Expr | None
        if raw in {"", "otherwise", "next"}:
            condition = None
        else:
            try:
                condition = parse_expr(raw)
            except Exception:
                condition = None
                line = int(transition.get("source", {}).get("line", 1))
                generated_diagnostics.append(
                    _warning(
                        "STIR_CONDITION_PROVENANCE_UNKNOWN",
                        f"`{raw}` could not be parsed for trigger/guard classification.",
                        line,
                    )
                )
        context = _context(
            model,
            machine,
            transition,
            products=products,
            sums=sums,
            functions=functions,
            externs=externs,
            aliases=aliases,
        )
        line = int(transition.get("source", {}).get("line", 1))
        classified = _classification(condition, context=context, line=line)
        trigger = classified["trigger"]
        guards = list(classified["guards"])
        unclassified = list(classified["unclassified_conditions"])
        generated_diagnostics.extend(classified["diagnostics"])
        transition["trigger"] = trigger
        transition["guards"] = guards
        transition["unclassified_conditions"] = unclassified
        transition["event"] = (
            None
            if trigger is None
            else (
                ("? " if trigger.get("role") == _ROLE_PROVISIONAL else "")
                + str(trigger.get("display", ""))
            )
        )
        transition["guard"] = "&".join(guards) or None
        transition["display_label"] = _display_label(
            trigger,
            guards,
            transition.get("action"),
            transition.get("failure_type"),
            unclassified,
        )
        transition["classification"] = {
            "confidence": (
                "unknown"
                if trigger is None
                else trigger.get("confidence", "unknown")
            ),
            "warning_count": len(classified["diagnostics"]),
        }
        transitions.append(transition)

    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
    seen = {
        (item.get("code"), item.get("line"), item.get("message"))
        for item in diagnostics
    }
    for item in generated_diagnostics:
        key = (item.get("code"), item.get("line"), item.get("message"))
        if key not in seen:
            diagnostics.append(item)
            seen.add(key)

    analysis = dict(result.get("analysis", {}))
    analysis.update(
        {
            "transition_ir_schema": STATE_TRANSITION_IR_SCHEMA,
            "transition_ir_version": STATE_TRANSITION_IR_VERSION,
            "confirmed_trigger_count": sum(
                1
                for item in transitions
                if (item.get("trigger") or {}).get("role") == _ROLE_CONFIRMED
            ),
            "inferred_trigger_count": sum(
                1
                for item in transitions
                if (item.get("trigger") or {}).get("role") == _ROLE_INFERRED
            ),
            "provisional_trigger_count": sum(
                1
                for item in transitions
                if (item.get("trigger") or {}).get("role") == _ROLE_PROVISIONAL
            ),
        }
    )
    result.update(
        {
            "transitions": transitions,
            "diagnostics": diagnostics,
            "analysis": analysis,
            "transition_ir": {
                "schema": STATE_TRANSITION_IR_SCHEMA,
                "version": STATE_TRANSITION_IR_VERSION,
            },
        }
    )
    return result

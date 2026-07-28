from __future__ import annotations

from pathlib import Path


PATH = Path("glyph/transition_input_provenance.py")
text = PATH.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"expected block not found:\n{old[:260]}")
    text = text.replace(old, new, 1)


replace_once(
    "from dataclasses import dataclass\n",
    "from dataclasses import dataclass, replace\n",
)

replace_once(
    '''def _resolve_discriminator(
    candidate: _Candidate,
    *,
    functions: Mapping[str, FunctionDecl],
) -> _Discriminator | None:
    definition = candidate.definition
    if not (
        isinstance(definition, CallExpr)
        and isinstance(definition.callee, NameExpr)
    ):
        return None
    decision = functions.get(definition.callee.name)
    if decision is None or not decision.guards:
        return None
    return _Discriminator(
        atom=candidate.atom,
        local_name=candidate.local_name,
        pattern=candidate.pattern,
        variant=candidate.variant,
        definition=definition,
        decision=decision,
    )
''',
    '''def _expand_lambda_calls(
    expression: Expr,
    lambdas: Mapping[str, object],
    visited: frozenset[str] = frozenset(),
) -> Expr:
    if isinstance(expression, FieldExpr):
        return FieldExpr(_expand_lambda_calls(expression.base, lambdas, visited), expression.field)
    if isinstance(expression, UnaryExpr):
        return UnaryExpr(expression.op, _expand_lambda_calls(expression.expr, lambdas, visited))
    if isinstance(expression, BinaryExpr):
        return BinaryExpr(
            expression.op,
            _expand_lambda_calls(expression.left, lambdas, visited),
            _expand_lambda_calls(expression.right, lambdas, visited),
        )
    if isinstance(expression, CallExpr):
        arguments = tuple(
            _expand_lambda_calls(argument, lambdas, visited)
            for argument in expression.args
        )
        if isinstance(expression.callee, NameExpr):
            lowering = lambdas.get(expression.callee.name)
            if lowering is not None and expression.callee.name not in visited and len(arguments) == 1:
                try:
                    body = parse_expr(str(lowering.body))
                except Exception:
                    return CallExpr(expression.callee, arguments)
                restored = _substitute(body, {str(lowering.parameter): arguments[0]})
                return _expand_lambda_calls(
                    restored,
                    lambdas,
                    visited | {expression.callee.name},
                )
        return CallExpr(expression.callee, arguments)
    if isinstance(expression, TryExpr):
        return TryExpr(_expand_lambda_calls(expression.expr, lambdas, visited))
    return expression


def _resolve_block_discriminator(
    candidate: _Candidate,
    definition: CallExpr,
    public: FunctionDecl,
    *,
    functions: Mapping[str, FunctionDecl],
    blocks: Mapping[str, object],
    lambdas: Mapping[str, object],
) -> _Discriminator | None:
    block = blocks.get(public.name)
    if block is None:
        return None
    try:
        final = parse_expr(str(block.final_source))
    except Exception:
        return None
    if not isinstance(final, NameExpr):
        return None
    bindings = list(block.bindings)
    final_indices = [index for index, binding in enumerate(bindings) if binding.name == final.name]
    if len(final_indices) != 1 or final_indices[0] != len(bindings) - 1:
        return None
    if len(public.params) != len(definition.args):
        return None

    available: dict[str, Expr] = {
        parameter.name: argument
        for parameter, argument in zip(public.params, definition.args)
    }
    for binding in bindings:
        helper = functions.get(binding.value_helper)
        if helper is None:
            return None
        try:
            helper_arguments = tuple(available[parameter.name] for parameter in helper.params)
        except KeyError:
            return None
        substitutions = {
            parameter.name: argument
            for parameter, argument in zip(helper.params, helper_arguments)
        }
        if binding.name == final.name:
            if binding.kind != "conditional" or not helper.guards:
                return None
            decision = replace(helper, name=public.name)
            return _Discriminator(
                atom=candidate.atom,
                local_name=candidate.local_name,
                pattern=candidate.pattern,
                variant=candidate.variant,
                definition=CallExpr(NameExpr(public.name), helper_arguments),
                decision=decision,
            )
        if binding.kind != "expression" or helper.expression is None or helper.guards:
            return None
        restored = _substitute(helper.expression, substitutions)
        available[binding.name] = _expand_lambda_calls(restored, lambdas)
    return None


def _resolve_discriminator(
    candidate: _Candidate,
    *,
    functions: Mapping[str, FunctionDecl],
    blocks: Mapping[str, object],
    lambdas: Mapping[str, object],
) -> _Discriminator | None:
    definition = candidate.definition
    if not (
        isinstance(definition, CallExpr)
        and isinstance(definition.callee, NameExpr)
    ):
        return None
    public = functions.get(definition.callee.name)
    if public is None:
        return None
    if public.guards:
        return _Discriminator(
            atom=candidate.atom,
            local_name=candidate.local_name,
            pattern=candidate.pattern,
            variant=candidate.variant,
            definition=definition,
            decision=public,
        )
    return _resolve_block_discriminator(
        candidate,
        definition,
        public,
        functions=functions,
        blocks=blocks,
        lambdas=lambdas,
    )
''',
)

replace_once(
    '''    functions = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, FunctionDecl)
    }
    definitions = _block_definitions(model, _next_name(machine))
''',
    '''    functions = {
        item.name: item
        for item in model.program.declarations
        if isinstance(item, FunctionDecl)
    }
    blocks = {item.name: item for item in model.blocks}
    lambdas = {item.name: item for item in model.lambdas}
    definitions = _block_definitions(model, _next_name(machine))
''',
)

replace_once(
    '''        discriminator = _resolve_discriminator(candidate, functions=functions)
''',
    '''        discriminator = _resolve_discriminator(
            candidate,
            functions=functions,
            blocks=blocks,
            lambdas=lambdas,
        )
''',
)

PATH.write_text(text, encoding="utf-8")

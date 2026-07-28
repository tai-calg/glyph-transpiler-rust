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
    '''def _resolve_block_discriminator(
    candidate: _Candidate,
    definition: CallExpr,
    public: FunctionDecl,
    *,
    functions: Mapping[str, FunctionDecl],
    blocks: Mapping[str, object],
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
        available[binding.name] = _substitute(helper.expression, substitutions)
    return None


def _resolve_discriminator(
    candidate: _Candidate,
    *,
    functions: Mapping[str, FunctionDecl],
    blocks: Mapping[str, object],
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
        )
''',
)

PATH.write_text(text, encoding="utf-8")

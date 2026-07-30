from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ..artifacts import CompilationModel
from ..compiler import CallExpr, Expr, ExternDecl, FunctionDecl, NameExpr, TryExpr, parse_expr
from ..function_blocks import FunctionBlockLowering
from .machine_relation import relation_by_transition_function
from .teir import (
    Assign,
    BasicBlock,
    Branch,
    EffectCall,
    Function,
    Instruction,
    Jump,
    Return,
    Terminator,
    TransitionCall,
)


@dataclass
class _BlockDraft:
    block_id: str
    instructions: list[Instruction] = field(default_factory=list)
    terminator: Terminator | None = None

    def freeze(self) -> BasicBlock:
        if self.terminator is None:
            raise ValueError(f"TEIR block {self.block_id} has no terminator")
        return BasicBlock(self.block_id, tuple(self.instructions), self.terminator)


class _Builder:
    def __init__(self) -> None:
        self.order: list[str] = []
        self.blocks: dict[str, _BlockDraft] = {}
        self.counter = 0

    def new_block(self, prefix: str) -> _BlockDraft:
        block_id = f"{prefix}.{self.counter}"
        self.counter += 1
        draft = _BlockDraft(block_id)
        self.order.append(block_id)
        self.blocks[block_id] = draft
        return draft

    def freeze(self) -> tuple[BasicBlock, ...]:
        return tuple(self.blocks[block_id].freeze() for block_id in self.order)


def lower_compilation_model(model: CompilationModel) -> dict[str, Function]:
    """Lower user-visible Glyph functions into one CFG representation.

    Generated continuation helpers remain an implementation detail of Rust code
    generation and are deliberately excluded.  Original ``:=`` blocks are
    lowered from ``CompilationModel.blocks`` so function-guard and block syntax
    converge before concrete or abstract execution.
    """

    relations = relation_by_transition_function(model)
    transition_functions = {
        name: relation.machine_id for name, relation in relations.items()
    }
    effects = frozenset(
        declaration.name
        for declaration in model.program.declarations
        if isinstance(declaration, ExternDecl)
    )
    blocks = {block.name: block for block in model.blocks}
    result: dict[str, Function] = {}
    for declaration in model.program.declarations:
        if not isinstance(declaration, FunctionDecl):
            continue
        if declaration.name.startswith("__glyph_block_"):
            continue
        result[declaration.name] = lower_function(
            declaration,
            block=blocks.get(declaration.name),
            transition_functions=transition_functions,
            effect_names=effects,
        )
    return result


def lower_function(
    declaration: FunctionDecl,
    *,
    block: FunctionBlockLowering | None = None,
    transition_functions: Mapping[str, str] = {},
    effect_names: frozenset[str] = frozenset(),
) -> Function:
    if block is not None:
        return _lower_block_function(
            declaration,
            block,
            transition_functions=transition_functions,
            effect_names=effect_names,
        )
    return _lower_decl_function(
        declaration,
        transition_functions=transition_functions,
        effect_names=effect_names,
    )


def _lower_decl_function(
    declaration: FunctionDecl,
    *,
    transition_functions: Mapping[str, str],
    effect_names: frozenset[str],
) -> Function:
    builder = _Builder()
    entry = builder.new_block("entry")
    if declaration.expression is not None:
        entry.terminator = Return(declaration.expression, declaration.line)
    elif declaration.guards:
        current = entry
        for index, clause in enumerate(declaration.guards):
            if clause.condition is None:
                current.terminator = Return(clause.value, clause.line)
                break
            selected = builder.new_block(f"guard{index}.selected")
            selected.terminator = Return(clause.value, clause.line)
            next_guard = builder.new_block(f"guard{index}.next")
            current.terminator = Branch(
                clause.condition,
                selected.block_id,
                next_guard.block_id,
                clause.line,
            )
            current = next_guard
        if current.terminator is None:
            current.terminator = Return(None, declaration.line)
    else:
        entry.terminator = Return(None, declaration.line)
    return Function(
        declaration.name,
        declaration.params,
        declaration.return_type,
        entry.block_id,
        builder.freeze(),
        declaration.line,
    )


def _lower_block_function(
    declaration: FunctionDecl,
    block: FunctionBlockLowering,
    *,
    transition_functions: Mapping[str, str],
    effect_names: frozenset[str],
) -> Function:
    builder = _Builder()
    current = builder.new_block("entry")
    for binding_index, binding in enumerate(block.bindings):
        if binding.kind == "conditional":
            current = _lower_conditional_binding(
                builder,
                current,
                binding.name,
                binding.source,
                binding.line,
                binding_index,
                transition_functions=transition_functions,
                effect_names=effect_names,
            )
            continue
        expression = parse_expr(binding.source)
        current.instructions.append(
            _lower_binding_instruction(
                binding.name,
                expression,
                binding.line,
                transition_functions=transition_functions,
                effect_names=effect_names,
            )
        )
    current.terminator = Return(parse_expr(block.final_source), block.final_line)
    return Function(
        declaration.name,
        declaration.params,
        declaration.return_type,
        "entry.0",
        builder.freeze(),
        declaration.line,
    )


def _lower_conditional_binding(
    builder: _Builder,
    current: _BlockDraft,
    target: str,
    source: str,
    line: int,
    binding_index: int,
    *,
    transition_functions: Mapping[str, str],
    effect_names: frozenset[str],
) -> _BlockDraft:
    clauses = _conditional_clauses(source, line)
    merge = builder.new_block(f"binding{binding_index}.merge")
    cursor = current
    for clause_index, (condition, value, clause_line) in enumerate(clauses):
        selected = builder.new_block(f"binding{binding_index}.case{clause_index}")
        selected.instructions.append(
            _lower_binding_instruction(
                target,
                value,
                clause_line,
                transition_functions=transition_functions,
                effect_names=effect_names,
            )
        )
        selected.terminator = Jump(merge.block_id)
        if condition is None:
            cursor.terminator = Jump(selected.block_id)
            break
        next_clause = builder.new_block(f"binding{binding_index}.next{clause_index}")
        cursor.terminator = Branch(
            condition,
            selected.block_id,
            next_clause.block_id,
            clause_line,
        )
        cursor = next_clause
    if cursor.terminator is None:
        cursor.terminator = Jump(merge.block_id)
    return merge


def _conditional_clauses(
    source: str,
    line: int,
) -> tuple[tuple[Expr | None, Expr, int], ...]:
    result: list[tuple[Expr | None, Expr, int]] = []
    for offset, original in enumerate(source.splitlines()):
        condition_text, separator, value_text = original.partition("=>")
        if not separator or not value_text.strip():
            raise ValueError(f"invalid conditional binding at line {line + offset}")
        condition_text = condition_text.strip()
        result.append(
            (
                None if condition_text == "_" else parse_expr(condition_text),
                parse_expr(value_text.strip()),
                line + offset,
            )
        )
    if not result or result[-1][0] is not None:
        raise ValueError(f"conditional binding at line {line} requires final fallback")
    return tuple(result)


def _lower_binding_instruction(
    target: str,
    expression: Expr,
    line: int,
    *,
    transition_functions: Mapping[str, str],
    effect_names: frozenset[str],
) -> Instruction:
    propagate_failure = isinstance(expression, TryExpr)
    value = expression.expr if isinstance(expression, TryExpr) else expression
    if isinstance(value, CallExpr) and isinstance(value.callee, NameExpr):
        name = value.callee.name
        machine = transition_functions.get(name)
        if machine is not None:
            return TransitionCall(
                target,
                machine,
                name,
                value.args,
                propagate_failure,
                line,
            )
        if name in effect_names:
            return EffectCall(target, name, value.args, propagate_failure, line)
    return Assign(target, expression, line)

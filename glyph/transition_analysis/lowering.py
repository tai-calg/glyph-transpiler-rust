from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ..artifacts import CompilationModel
from ..compiler import CallExpr, Expr, ExternDecl, FunctionDecl, NameExpr, TryExpr
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


@dataclass(frozen=True)
class LoweringIssue:
    function: str
    line: int
    reason: str

    def to_ir(self) -> dict[str, object]:
        return {
            "function": self.function,
            "line": self.line,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LoweringReport:
    functions: Mapping[str, Function]
    issues: tuple[LoweringIssue, ...]


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


def lower_compilation_model(
    model: CompilationModel,
    *,
    strict: bool = True,
) -> dict[str, Function]:
    """Lower user-visible Glyph functions into one CFG representation.

    ``strict=True`` is used by the concrete oracle and tests so unsupported
    lowering cannot be hidden.  The public shadow pipeline uses ``strict=False``
    through ``lower_compilation_model_report``; one unsupported helper then
    becomes an explicit issue instead of breaking ordinary compilation.
    """

    report = lower_compilation_model_report(model)
    if strict and report.issues:
        issue = report.issues[0]
        raise ValueError(
            f"TEIR lowering failed for {issue.function} at line {issue.line}: "
            f"{issue.reason}"
        )
    return dict(report.functions)


def lower_compilation_model_report(model: CompilationModel) -> LoweringReport:
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
    declarations = {
        declaration.name: declaration
        for declaration in model.program.declarations
        if isinstance(declaration, FunctionDecl)
    }
    result: dict[str, Function] = {}
    issues: list[LoweringIssue] = []
    for declaration in declarations.values():
        if declaration.name.startswith("__glyph_block_"):
            continue
        try:
            result[declaration.name] = lower_function(
                declaration,
                block=blocks.get(declaration.name),
                helper_functions=declarations,
                transition_functions=transition_functions,
                effect_names=effects,
            )
        except (TypeError, ValueError) as error:
            issues.append(
                LoweringIssue(
                    declaration.name,
                    declaration.line,
                    str(error) or type(error).__name__,
                )
            )
    return LoweringReport(dict(result), tuple(issues))


def lower_function(
    declaration: FunctionDecl,
    *,
    block: FunctionBlockLowering | None = None,
    helper_functions: Mapping[str, FunctionDecl] | None = None,
    transition_functions: Mapping[str, str] | None = None,
    effect_names: frozenset[str] = frozenset(),
) -> Function:
    transition_functions = transition_functions or {}
    helper_functions = helper_functions or {}
    if block is not None:
        return _lower_block_function(
            declaration,
            block,
            helper_functions=helper_functions,
            transition_functions=transition_functions,
            effect_names=effect_names,
        )
    return _lower_decl_function(declaration)


def _lower_decl_function(declaration: FunctionDecl) -> Function:
    builder = _Builder()
    entry = builder.new_block("entry")
    _terminate_with_declaration(builder, entry, declaration, prefix="guard")
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
    helper_functions: Mapping[str, FunctionDecl],
    transition_functions: Mapping[str, str],
    effect_names: frozenset[str],
) -> Function:
    builder = _Builder()
    current = builder.new_block("entry")
    for binding_index, binding in enumerate(block.bindings):
        helper = helper_functions.get(binding.value_helper)
        if helper is None:
            raise ValueError(
                f"compiler helper {binding.value_helper} is unavailable for TEIR lowering"
            )
        if helper.guards:
            current = _lower_guarded_binding(
                builder,
                current,
                binding.name,
                helper,
                binding_index,
                transition_functions=transition_functions,
                effect_names=effect_names,
            )
            continue
        if helper.expression is None:
            raise ValueError(
                f"compiler helper {binding.value_helper} has no value expression"
            )
        current.instructions.append(
            _lower_binding_instruction(
                binding.name,
                helper.expression,
                binding.line,
                transition_functions=transition_functions,
                effect_names=effect_names,
            )
        )

    final_helper = helper_functions.get(block.final_helper)
    if final_helper is None:
        raise ValueError(
            f"compiler helper {block.final_helper} is unavailable for TEIR lowering"
        )
    _terminate_with_declaration(
        builder,
        current,
        final_helper,
        prefix="final",
    )
    return Function(
        declaration.name,
        declaration.params,
        declaration.return_type,
        "entry.0",
        builder.freeze(),
        declaration.line,
    )


def _terminate_with_declaration(
    builder: _Builder,
    current: _BlockDraft,
    declaration: FunctionDecl,
    *,
    prefix: str,
) -> None:
    if declaration.expression is not None:
        current.terminator = Return(declaration.expression, declaration.line)
        return
    if not declaration.guards:
        current.terminator = Return(None, declaration.line)
        return
    cursor = current
    for index, clause in enumerate(declaration.guards):
        if clause.condition is None:
            cursor.terminator = Return(clause.value, clause.line)
            return
        selected = builder.new_block(f"{prefix}{index}.selected")
        selected.terminator = Return(clause.value, clause.line)
        next_guard = builder.new_block(f"{prefix}{index}.next")
        cursor.terminator = Branch(
            clause.condition,
            selected.block_id,
            next_guard.block_id,
            clause.line,
        )
        cursor = next_guard
    cursor.terminator = Return(None, declaration.line)


def _lower_guarded_binding(
    builder: _Builder,
    current: _BlockDraft,
    target: str,
    helper: FunctionDecl,
    binding_index: int,
    *,
    transition_functions: Mapping[str, str],
    effect_names: frozenset[str],
) -> _BlockDraft:
    merge = builder.new_block(f"binding{binding_index}.merge")
    cursor = current
    for clause_index, clause in enumerate(helper.guards):
        selected = builder.new_block(f"binding{binding_index}.case{clause_index}")
        selected.instructions.append(
            _lower_binding_instruction(
                target,
                clause.value,
                clause.line,
                transition_functions=transition_functions,
                effect_names=effect_names,
            )
        )
        selected.terminator = Jump(merge.block_id)
        if clause.condition is None:
            cursor.terminator = Jump(selected.block_id)
            return merge
        next_clause = builder.new_block(f"binding{binding_index}.next{clause_index}")
        cursor.terminator = Branch(
            clause.condition,
            selected.block_id,
            next_clause.block_id,
            clause.line,
        )
        cursor = next_clause
    cursor.terminator = Jump(merge.block_id)
    return merge


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

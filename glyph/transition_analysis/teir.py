from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from ..compiler import Expr, Param, TypeRef


@dataclass(frozen=True)
class Assign:
    """Evaluate one expression once and bind the result to ``target``."""

    target: str
    expression: Expr
    line: int


@dataclass(frozen=True)
class TransitionCall:
    """Invoke one normalized Machine transition relation."""

    target: str
    machine: str
    function: str
    arguments: tuple[Expr, ...]
    propagate_failure: bool
    line: int


@dataclass(frozen=True)
class EffectCall:
    """Invoke one external Effect boundary."""

    target: str | None
    operation: str
    arguments: tuple[Expr, ...]
    propagate_failure: bool
    line: int


Instruction: TypeAlias = Assign | TransitionCall | EffectCall


@dataclass(frozen=True)
class Jump:
    target: str


@dataclass(frozen=True)
class Branch:
    condition: Expr
    true_block: str
    false_block: str
    line: int


@dataclass(frozen=True)
class Return:
    value: Expr | None
    line: int


@dataclass(frozen=True)
class PropagateFailure:
    error: Expr
    line: int


Terminator: TypeAlias = Jump | Branch | Return | PropagateFailure


@dataclass(frozen=True)
class BasicBlock:
    block_id: str
    instructions: tuple[Instruction, ...]
    terminator: Terminator


@dataclass(frozen=True)
class Function:
    """CFG form used by both the concrete and abstract transition analyzers."""

    function_id: str
    parameters: tuple[Param, ...]
    return_type: TypeRef
    entry_block: str
    blocks: tuple[BasicBlock, ...]
    source_line: int

    @property
    def block_map(self) -> dict[str, BasicBlock]:
        return {block.block_id: block for block in self.blocks}

    def to_ir(self) -> dict[str, object]:
        return {
            "function_id": self.function_id,
            "parameters": [
                {"name": parameter.name, "type": _render_type(parameter.ty)}
                for parameter in self.parameters
            ],
            "return_type": _render_type(self.return_type),
            "entry_block": self.entry_block,
            "source_line": self.source_line,
            "blocks": [_block_to_ir(block) for block in self.blocks],
        }


def _block_to_ir(block: BasicBlock) -> dict[str, object]:
    return {
        "block_id": block.block_id,
        "instructions": [_instruction_to_ir(item) for item in block.instructions],
        "terminator": _terminator_to_ir(block.terminator),
    }


def _instruction_to_ir(instruction: Instruction) -> dict[str, object]:
    if isinstance(instruction, Assign):
        return {
            "kind": "assign",
            "target": instruction.target,
            "expression": repr(instruction.expression),
            "line": instruction.line,
        }
    if isinstance(instruction, TransitionCall):
        return {
            "kind": "transition-call",
            "target": instruction.target,
            "machine": instruction.machine,
            "function": instruction.function,
            "arguments": [repr(argument) for argument in instruction.arguments],
            "propagate_failure": instruction.propagate_failure,
            "line": instruction.line,
        }
    return {
        "kind": "effect-call",
        "target": instruction.target,
        "operation": instruction.operation,
        "arguments": [repr(argument) for argument in instruction.arguments],
        "propagate_failure": instruction.propagate_failure,
        "line": instruction.line,
    }


def _terminator_to_ir(terminator: Terminator) -> dict[str, object]:
    if isinstance(terminator, Jump):
        return {"kind": "jump", "target": terminator.target}
    if isinstance(terminator, Branch):
        return {
            "kind": "branch",
            "condition": repr(terminator.condition),
            "true_block": terminator.true_block,
            "false_block": terminator.false_block,
            "line": terminator.line,
        }
    if isinstance(terminator, Return):
        return {"kind": "return", "value": repr(terminator.value), "line": terminator.line}
    return {"kind": "propagate-failure", "error": repr(terminator.error), "line": terminator.line}


def _render_type(type_ref: TypeRef) -> str:
    if not type_ref.args:
        return type_ref.name
    return f"{type_ref.name}<{','.join(_render_type(item) for item in type_ref.args)}>"

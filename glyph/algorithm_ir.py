from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Mapping, Sequence

from .compiler import ExternDecl, FunctionDecl, Program, TypeRef
from .function_blocks import FunctionBlockLowering
from .opaque import OpaqueDecl
from .pipeline import LambdaLowering, _parse_lambda, _render_type, _split_pipeline


@dataclass(frozen=True)
class AlgorithmSourceRef:
    line: int
    column: int = 1


@dataclass(frozen=True)
class AlgorithmBranch:
    condition: str
    value: str
    binders: tuple[str, ...]
    source: AlgorithmSourceRef


@dataclass(frozen=True)
class AlgorithmStage:
    kind: str
    name: str
    label: str
    input_type: str | None
    output_type: str | None
    propagates: bool
    source: AlgorithmSourceRef


@dataclass(frozen=True)
class AlgorithmValue:
    kind: str
    source_text: str
    result_type: str
    source: AlgorithmSourceRef
    input_text: str | None = None
    input_type: str | None = None
    branches: tuple[AlgorithmBranch, ...] = ()
    stages: tuple[AlgorithmStage, ...] = ()


@dataclass(frozen=True)
class AlgorithmStep:
    kind: str
    name: str | None
    type: str
    value: AlgorithmValue
    source: AlgorithmSourceRef


@dataclass(frozen=True)
class AlgorithmFunction:
    name: str
    return_type: str
    source: AlgorithmSourceRef
    steps: tuple[AlgorithmStep, ...]


@dataclass(frozen=True)
class AlgorithmIR:
    source_name: str
    functions: tuple[AlgorithmFunction, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _Signature:
    params: tuple[TypeRef, ...]
    result: TypeRef
    kind: str


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].rstrip()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _unwrap_result(ty: TypeRef) -> TypeRef | None:
    if ty.name == "R" and len(ty.args) == 2:
        return ty.args[0]
    return None


def _signatures(program: Program, opaques: Sequence[OpaqueDecl]) -> dict[str, _Signature]:
    opaque_names = {item.name for item in opaques}
    result: dict[str, _Signature] = {}
    for declaration in program.declarations:
        if isinstance(declaration, FunctionDecl):
            if declaration.name.startswith("__glyph_"):
                continue
            result[declaration.name] = _Signature(
                tuple(param.ty for param in declaration.params),
                declaration.return_type,
                "function",
            )
        elif isinstance(declaration, ExternDecl):
            result[declaration.name] = _Signature(
                tuple(param.ty for param in declaration.params),
                declaration.return_type,
                "rust" if declaration.name in opaque_names else "effect",
            )
    return result


def _function_declarations(program: Program) -> dict[str, FunctionDecl]:
    return {
        declaration.name: declaration
        for declaration in program.declarations
        if isinstance(declaration, FunctionDecl)
        and not declaration.name.startswith("__glyph_")
    }


def _branch_binders(condition: str) -> tuple[str, ...]:
    match = re.search(r"==\s*[A-Z][A-Za-z0-9_]*\((.*)\)\s*$", condition)
    if match is None:
        return ()
    names: list[str] = []
    for item in match.group(1).split(","):
        value = item.strip()
        if value == "_" or not re.fullmatch(r"[a-z_][A-Za-z0-9_]*", value):
            continue
        if value not in names:
            names.append(value)
    return tuple(names)


def _conditional_source(
    source_lines: Sequence[str], binding_line: int, fallback: str
) -> tuple[AlgorithmBranch, ...]:
    index = binding_line - 1
    if not 0 <= index < len(source_lines):
        return _fallback_branches(fallback, binding_line)
    base = _indent(source_lines[index])
    branches: list[AlgorithmBranch] = []
    cursor = index + 1
    while cursor < len(source_lines):
        clean = _strip_comment(source_lines[cursor])
        if not clean.strip():
            cursor += 1
            continue
        if _indent(clean) <= base:
            break
        stripped = clean.strip()
        separator = ">>" if ">>" in stripped else "=>" if "=>" in stripped else None
        if separator is None:
            cursor += 1
            continue
        condition, value = (part.strip() for part in stripped.split(separator, 1))
        branches.append(
            AlgorithmBranch(
                condition,
                value,
                _branch_binders(condition),
                AlgorithmSourceRef(cursor + 1),
            )
        )
        cursor += 1
    return tuple(branches) if branches else _fallback_branches(fallback, binding_line)


def _fallback_branches(source: str, line: int) -> tuple[AlgorithmBranch, ...]:
    result: list[AlgorithmBranch] = []
    for offset, item in enumerate(source.splitlines(), start=1):
        separator = "=>" if "=>" in item else ">>" if ">>" in item else None
        if separator is None:
            continue
        condition, value = (part.strip() for part in item.split(separator, 1))
        result.append(
            AlgorithmBranch(
                condition,
                value,
                _branch_binders(condition),
                AlgorithmSourceRef(line + offset),
            )
        )
    return tuple(result)


def _pipeline_lines(
    source_lines: Sequence[str], statement_line: int, parts: Sequence[str]
) -> tuple[int, ...]:
    if len(parts) <= 1:
        return (statement_line,)
    index = statement_line - 1
    if not 0 <= index < len(source_lines):
        return tuple(statement_line for _ in parts)
    original = _strip_comment(source_lines[index])
    base = _indent(original)
    stripped = original.strip()
    assignment = stripped.find(":=")
    rhs = stripped[assignment + 2 :].strip() if assignment >= 0 else stripped
    locations: list[int] = [statement_line]
    if rhs and "/>" in rhs:
        locations.extend(statement_line for _ in parts[1:])
        return tuple(locations)
    cursor = index + 1
    while cursor < len(source_lines) and len(locations) < len(parts):
        clean = _strip_comment(source_lines[cursor])
        if not clean.strip():
            cursor += 1
            continue
        if _indent(clean) <= base:
            break
        item = clean.strip()
        if len(locations) == 1 and not rhs and not item.startswith("/>"):
            locations[0] = cursor + 1
        elif item.startswith("/>"):
            locations.append(cursor + 1)
        cursor += 1
    while len(locations) < len(parts):
        locations.append(statement_line)
    return tuple(locations)


def _lambda_match(
    lambdas: Sequence[LambdaLowering],
    used: set[int],
    line: int,
    body: str,
) -> LambdaLowering | None:
    for index, item in enumerate(lambdas):
        if index in used:
            continue
        if item.body == body and item.line == line:
            used.add(index)
            return item
    for index, item in enumerate(lambdas):
        if index in used:
            continue
        if item.body == body:
            used.add(index)
            return item
    return None


def _simple_type(text: str, locals_: Mapping[str, TypeRef]) -> TypeRef | None:
    value = text.strip()
    return locals_.get(value) if value.isidentifier() else None


def _expression_value(
    *,
    text: str,
    line: int,
    result_type: TypeRef,
    source_lines: Sequence[str],
    locals_: Mapping[str, TypeRef],
    signatures: Mapping[str, _Signature],
    lambdas: Sequence[LambdaLowering],
    used_lambdas: set[int],
) -> AlgorithmValue:
    if "/>" not in text:
        return AlgorithmValue(
            "expression",
            text,
            _render_type(result_type),
            AlgorithmSourceRef(line),
        )

    parts = _split_pipeline(text)
    locations = _pipeline_lines(source_lines, line, parts)
    current_type = _simple_type(parts[0], locals_)
    stages: list[AlgorithmStage] = []
    for stage_index, stage_text in enumerate(parts[1:], start=1):
        stage_line = locations[stage_index]
        if stage_text.startswith("|"):
            parameter, _, body = _parse_lambda(stage_text, stage_line)
            lowering = _lambda_match(lambdas, used_lambdas, stage_line, body)
            input_type = lowering.parameter_type if lowering is not None else current_type
            output_type = lowering.result_type if lowering is not None else None
            stages.append(
                AlgorithmStage(
                    "lambda",
                    parameter,
                    f"λ {parameter} → {body}",
                    None if input_type is None else _render_type(input_type),
                    None if output_type is None else _render_type(output_type),
                    False,
                    AlgorithmSourceRef(stage_line),
                )
            )
            current_type = output_type
            continue

        propagates = stage_text.endswith("?")
        name = stage_text[:-1].strip() if propagates else stage_text.strip()
        signature = signatures.get(name)
        input_type = signature.params[0] if signature and signature.params else current_type
        raw_output = signature.result if signature else None
        output_type = _unwrap_result(raw_output) if propagates and raw_output else raw_output
        kind = signature.kind if signature else "function"
        stages.append(
            AlgorithmStage(
                kind,
                name,
                name + ("?" if propagates else ""),
                None if input_type is None else _render_type(input_type),
                None if output_type is None else _render_type(output_type),
                propagates,
                AlgorithmSourceRef(stage_line),
            )
        )
        current_type = output_type

    return AlgorithmValue(
        "pipeline",
        text,
        _render_type(result_type),
        AlgorithmSourceRef(line),
        input_text=parts[0],
        input_type=None if _simple_type(parts[0], locals_) is None else _render_type(_simple_type(parts[0], locals_)),
        stages=tuple(stages),
    )


def build_algorithm_ir(
    source: str,
    source_name: str,
    program: Program,
    blocks: Sequence[FunctionBlockLowering],
    lambdas: Sequence[LambdaLowering],
    opaques: Sequence[OpaqueDecl],
) -> AlgorithmIR:
    source_lines = source.splitlines()
    declarations = _function_declarations(program)
    signatures = _signatures(program, opaques)
    used_lambdas: set[int] = set()
    functions: list[AlgorithmFunction] = []

    for block in blocks:
        declaration = declarations.get(block.name)
        if declaration is None:
            continue
        locals_: dict[str, TypeRef] = {
            parameter.name: parameter.ty for parameter in declaration.params
        }
        steps: list[AlgorithmStep] = []
        for binding in block.bindings:
            if binding.kind == "conditional":
                value = AlgorithmValue(
                    "conditional",
                    binding.source.replace("=>", ">>"),
                    _render_type(binding.type_ref),
                    AlgorithmSourceRef(binding.line),
                    branches=_conditional_source(source_lines, binding.line, binding.source),
                )
            else:
                value = _expression_value(
                    text=binding.source,
                    line=binding.line,
                    result_type=binding.type_ref,
                    source_lines=source_lines,
                    locals_=locals_,
                    signatures=signatures,
                    lambdas=lambdas,
                    used_lambdas=used_lambdas,
                )
            steps.append(
                AlgorithmStep(
                    "binding",
                    binding.name,
                    _render_type(binding.type_ref),
                    value,
                    AlgorithmSourceRef(binding.line),
                )
            )
            locals_[binding.name] = binding.type_ref

        final_value = _expression_value(
            text=block.final_source,
            line=block.final_line,
            result_type=declaration.return_type,
            source_lines=source_lines,
            locals_=locals_,
            signatures=signatures,
            lambdas=lambdas,
            used_lambdas=used_lambdas,
        )
        steps.append(
            AlgorithmStep(
                "return",
                None,
                _render_type(declaration.return_type),
                final_value,
                AlgorithmSourceRef(block.final_line),
            )
        )
        functions.append(
            AlgorithmFunction(
                block.name,
                _render_type(declaration.return_type),
                AlgorithmSourceRef(block.line),
                tuple(steps),
            )
        )

    return AlgorithmIR(source_name, tuple(functions))

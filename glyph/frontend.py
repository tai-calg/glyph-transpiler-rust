from __future__ import annotations

from pathlib import Path

from .compiler import Program, parse_program as _parse_program
from .machine import MachineDecl, extract_machines, validate_machines
from .pattern_codegen import PatternRustGenerator
from .syntax import expand_compact_syntax
from .temporal import SpecDecl, extract_specs
from .temporal_codegen import append_temporal_rust
from .temporal_stream_codegen import append_streaming_temporal_rust
from .temporal_stream_safety_codegen import append_safety_streaming_temporal_rust
from .temporal_validate import validate_temporal_specs


def _parse(
    source: str,
) -> tuple[Program, tuple[SpecDecl, ...], tuple[MachineDecl, ...]]:
    expanded = expand_compact_syntax(source)
    without_specs, specs = extract_specs(expanded)
    core, machines = extract_machines(without_specs)
    program = _parse_program(core)
    validate_temporal_specs(program, specs)
    validate_machines(program, machines)
    return program, specs, machines


def parse_program(source: str) -> Program:
    program, _, _ = _parse(source)
    return program


def compile_source(source: str) -> str:
    program, specs, _ = _parse(source)
    logic = append_temporal_rust(PatternRustGenerator(program).generate(), program, specs)
    logic = append_streaming_temporal_rust(logic, program, specs)
    return append_safety_streaming_temporal_rust(logic, program, specs)


def compile_file(input_path: str | Path, output_path: str | Path) -> None:
    source = Path(input_path).read_text(encoding="utf-8")
    generated = compile_source(source)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(generated, encoding="utf-8")

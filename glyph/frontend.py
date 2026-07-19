from __future__ import annotations

from pathlib import Path

from .compiler import Program, RustGenerator, parse_program as _parse_program
from .syntax import expand_compact_syntax
from .temporal import extract_specs
from .temporal_codegen import append_temporal_rust


def _parse(source: str) -> tuple[Program, tuple[object, ...]]:
    expanded = expand_compact_syntax(source)
    core, specs = extract_specs(expanded)
    return _parse_program(core), specs


def parse_program(source: str) -> Program:
    program, _ = _parse(source)
    return program


def compile_source(source: str) -> str:
    program, specs = _parse(source)
    return append_temporal_rust(RustGenerator(program).generate(), program, specs)


def compile_file(input_path: str | Path, output_path: str | Path) -> None:
    source = Path(input_path).read_text(encoding="utf-8")
    generated = compile_source(source)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(generated, encoding="utf-8")

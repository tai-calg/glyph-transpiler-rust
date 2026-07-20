from __future__ import annotations

from pathlib import Path

from .artifacts import compile_artifacts, parse_compilation_model
from .compiler import Program


def parse_program(source: str) -> Program:
    return parse_compilation_model(source).program


def compile_source(source: str) -> str:
    return compile_artifacts(source).logic


def compile_file(input_path: str | Path, output_path: str | Path) -> None:
    source = Path(input_path).read_text(encoding="utf-8")
    generated = compile_source(source)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(generated, encoding="utf-8")

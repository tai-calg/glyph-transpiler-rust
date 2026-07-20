from __future__ import annotations

import json
from pathlib import Path
from typing import TextIO

from .artifacts import parse_compilation_model
from .incremental import IncrementalCompiler


_HELP = """Commands:
  :check              recompile the current file
  :symbols            list interned symbols
  :type NAME          show the resolved type of a symbol
  :ast NAME           print a function's typed expression tree
  :diagram            regenerate Mermaid diagrams
  :reload             reload the source file
  :help               show this help
  :quit               exit
"""


class ReplSession:
    def __init__(self, input_path: str | Path, diagram_dir: str | Path | None = None):
        self.input_path = Path(input_path)
        self.diagram_dir = Path(diagram_dir) if diagram_dir is not None else self.input_path.parent / ".glyph" / self.input_path.stem
        self.compiler = IncrementalCompiler()
        self._source = ""
        self._model = None
        self.reload()

    def reload(self) -> str:
        self._source = self.input_path.read_text(encoding="utf-8")
        self._model = parse_compilation_model(self._source)
        self.compiler.compile_text(self._source, str(self.input_path))
        return "ok"

    @property
    def model(self):
        assert self._model is not None
        return self._model

    def execute(self, command: str) -> tuple[str, bool]:
        text = command.strip()
        if text in {":quit", ":q"}:
            return "", True
        if text in {":help", ":h", ""}:
            return _HELP.rstrip(), False
        if text in {":reload", ":r"}:
            return self.reload(), False
        if text == ":check":
            result = self.compiler.compile_text(self._source, str(self.input_path))
            return f"ok {result.snapshot.digest[:12]}", False
        if text == ":symbols":
            lines = [
                f"{record.id.value:04d} {record.kind:<18} {record.name}"
                + ("" if record.type_name is None else f" : {record.type_name}")
                for record in self.model.semantic.symbols
            ]
            return "\n".join(lines), False
        if text.startswith(":type "):
            name = text[6:].strip()
            record = self.model.semantic.symbol(name)
            if record is None:
                return f"unknown symbol: {name}", False
            return record.type_name or record.kind, False
        if text.startswith(":ast "):
            name = text[5:].strip()
            function = self.model.semantic.function(name)
            if function is None:
                return f"unknown function: {name}", False
            return json.dumps(function.to_dict(), ensure_ascii=False, indent=2), False
        if text == ":diagram":
            result = self.compiler.compile_path(self.input_path, diagram_dir=self.diagram_dir)
            return str(self.diagram_dir), False
        return "commands must start with ':'; use :help", False


def run_repl(
    input_path: str | Path,
    diagram_dir: str | Path | None = None,
    *,
    stdin: TextIO,
    stdout: TextIO,
) -> int:
    session = ReplSession(input_path, diagram_dir)
    stdout.write("Glyph development REPL. :help for commands.\n")
    while True:
        stdout.write("glyph> ")
        stdout.flush()
        line = stdin.readline()
        if line == "":
            return 0
        output, done = session.execute(line)
        if output:
            stdout.write(output + "\n")
        if done:
            return 0

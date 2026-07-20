from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import time
from typing import Callable

from .artifacts import RustArtifacts, compile_artifacts, parse_compilation_model
from .mermaid import DiagramBundle, compile_diagram_bundle


@dataclass(frozen=True)
class CompilationSnapshot:
    digest: str
    artifacts: RustArtifacts
    diagrams: DiagramBundle
    semantic_json: str


@dataclass(frozen=True)
class IncrementalResult:
    changed: bool
    snapshot: CompilationSnapshot
    written: tuple[Path, ...]


def _digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    return True


def _design_json(model) -> str:
    payload = model.semantic.to_dict()
    payload["lambdas"] = [asdict(item) for item in model.lambdas]
    payload["architecture"] = model.architecture.to_dict()
    payload["rust_todos"] = [item.to_dict() for item in model.opaques]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


class IncrementalCompiler:
    """Content-addressed one-file compiler cache used by watch mode and the Studio."""

    def __init__(self) -> None:
        self._cache: dict[str, CompilationSnapshot] = {}
        self._last_digest: str | None = None

    def compile_text(
        self,
        source: str,
        source_name: str = "input.glyph",
        source_href: str | None = None,
    ) -> IncrementalResult:
        digest = _digest(source)
        cached = self._cache.get(digest)
        if cached is None:
            model = parse_compilation_model(source, source_name)
            artifacts = compile_artifacts(source)
            diagrams = compile_diagram_bundle(source, source_name, source_href)
            cached = CompilationSnapshot(
                digest, artifacts, diagrams, _design_json(model)
            )
            self._cache[digest] = cached
        changed = digest != self._last_digest
        self._last_digest = digest
        return IncrementalResult(changed, cached, ())

    def compile_path(
        self,
        input_path: str | Path,
        *,
        logic_output: str | Path | None = None,
        host_output: str | Path | None = None,
        diagram_dir: str | Path | None = None,
        ast_output: str | Path | None = None,
    ) -> IncrementalResult:
        input_file = Path(input_path)
        source = input_file.read_text(encoding="utf-8")
        source_href = None
        if diagram_dir is not None:
            import os

            source_href = os.path.relpath(input_file, Path(diagram_dir)).replace(
                os.sep, "/"
            )
        result = self.compile_text(source, str(input_file), source_href)
        written: list[Path] = []
        if logic_output is not None:
            path = Path(logic_output)
            if _write_if_changed(path, result.snapshot.artifacts.logic):
                written.append(path)
        if host_output is not None:
            path = Path(host_output)
            if _write_if_changed(path, result.snapshot.artifacts.host):
                written.append(path)
        if diagram_dir is not None:
            destination = Path(diagram_dir)
            for name, content in result.snapshot.diagrams.files.items():
                path = destination / name
                if _write_if_changed(path, content):
                    written.append(path)
        if ast_output is not None:
            path = Path(ast_output)
            if _write_if_changed(path, result.snapshot.semantic_json):
                written.append(path)
        return IncrementalResult(result.changed, result.snapshot, tuple(written))


def watch_file(
    compiler: IncrementalCompiler,
    input_path: str | Path,
    *,
    logic_output: str | Path | None = None,
    host_output: str | Path | None = None,
    diagram_dir: str | Path | None = None,
    ast_output: str | Path | None = None,
    interval: float = 0.5,
    once: bool = False,
    on_result: Callable[[IncrementalResult], None] | None = None,
) -> None:
    """Poll one source file and regenerate only when its content hash changes."""

    if interval < 0.1:
        raise ValueError("watch interval must be at least 0.1 seconds")
    while True:
        result = compiler.compile_path(
            input_path,
            logic_output=logic_output,
            host_output=host_output,
            diagram_dir=diagram_dir,
            ast_output=ast_output,
        )
        if on_result is not None:
            on_result(result)
        if once:
            return
        time.sleep(interval)

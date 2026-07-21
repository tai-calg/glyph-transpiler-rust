from __future__ import annotations

import json
from pathlib import Path

from glyph import CompilationPipeline

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = {
    "door": ROOT / "examples" / "acceptance" / "door_controller.glyph",
    "batch": ROOT / "examples" / "acceptance" / "job_scheduler.glyph",
    "motor": ROOT / "examples" / "acceptance" / "motor_safety.glyph",
}
SCHEMAS = {
    "architecture-ir.json": "glyph.architecture-ir",
    "algorithm-ir.json": "glyph.algorithm-ir",
    "execution-ir.json": "glyph.execution-ir",
    "source-map.json": "glyph.source-map",
    "preprocessor-map.json": "glyph.preprocessor-map",
}


def compile_example(name: str):
    path = EXAMPLES[name]
    source = path.read_text(encoding="utf-8")
    relative = str(path.relative_to(ROOT))
    return CompilationPipeline().compile_text(source, relative, relative)


def load(outputs, filename: str):
    return json.loads(outputs.diagrams.files[filename])


def stages(algorithm: dict[str, object]) -> list[dict[str, object]]:
    result = []
    for function in algorithm.get("functions", []):
        for step in function.get("steps", []):
            result.extend(step.get("value", {}).get("stages", []))
    return result

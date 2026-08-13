from __future__ import annotations

from pathlib import Path

from glyph import parse_compilation_model
from glyph.assembly_frontend import AssemblyCompilationModel


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly_basic.glyph"


def test_assembly_basic_example_stays_compilable() -> None:
    """Keep the public Assembly syntax example synchronized with the parser."""

    source = EXAMPLE.read_text(encoding="utf-8")
    model = parse_compilation_model(source)

    assert isinstance(model, AssemblyCompilationModel)
    assert [assembly.name for assembly in model.assemblies] == ["BuildingControl"]

    ir = model.assembly_ir[0]
    assert [(instance["name"], instance["machine"]) for instance in ir.instances] == [
        ("door", "Door"),
        ("alarm", "Alarm"),
    ]
    assert [
        (
            route["source_instance"],
            route["effect"],
            route["target_instance"],
            route["target_input"],
        )
        for route in ir.routes
    ] == [("door", "notify_alarm", "alarm", "input")]

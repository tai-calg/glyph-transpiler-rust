from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    if content.count(old) != 1:
        raise SystemExit(f"expected exactly one match in {path}: {old!r}")
    file_path.write_text(content.replace(old, new), encoding="utf-8")


replace_once(
    "glyph/state_diagram_workspace.py",
    "const spreadX=manual?1:clamp(1+Math.max(0,complexity-2.4)*.46,1,2.9);",
    "const spreadX=manual?1:clamp(1+Math.max(0,complexity-2.4)*.72,1,3.8);",
)
replace_once(
    "tests/test_layout_state_diagram_workspace.py",
    '"complexity-2.4)*.46",',
    '"complexity-2.4)*.72",',
)

Path(__file__).unlink()

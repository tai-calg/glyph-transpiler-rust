from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    if content.count(old) != 1:
        raise SystemExit(f"expected exactly one match in {path}: {old!r}")
    file_path.write_text(content.replace(old, new), encoding="utf-8")


replace_once(
    "glyph/state_diagram_workspace.py",
    '  const spreadX=manual?1:clamp(1+Math.max(0,complexity-1.9)*.22,1,2.35);\n'
    '  const spreadY=manual?1:clamp(1+Math.max(0,complexity-2.35)*.15,1,1.9);',
    '  const spreadX=manual?1:clamp(1+Math.max(0,complexity-2.4)*.46,1,2.9);\n'
    '  const spreadY=manual?1:clamp(1+Math.max(0,complexity-2.8)*.24,1,2.2);',
)

replace_once(
    "glyph/adaptive_state_focus.py",
    '    spreadAdaptiveNodes(stage,machine);\n'
    '    window.glyphStateDiagramWorkspace?.prepare?.(stage,machine);\n'
    '    const complete=()=>{\n'
    '      window.glyphTransitionIoClusters?.reroute?.(stage);\n'
    '      const bounds=occupiedBounds(stage);',
    '    const complete=()=>{\n'
    '      const bounds=occupiedBounds(stage);',
)

replace_once(
    "tests/verify_adaptive_state_workspace.mjs",
    '      adaptiveFactorX: Number(stage?.dataset.adaptiveStateSpreadFactorX || 0),\n'
    '      adaptiveFactorY: Number(stage?.dataset.adaptiveStateSpreadFactorY || 0),\n',
    '',
)
replace_once(
    "tests/verify_adaptive_state_workspace.mjs",
    '  assert(audit.adaptiveFactorX > 1.1, JSON.stringify(audit));\n'
    '  assert(audit.adaptiveFactorY >= 1, JSON.stringify(audit));\n',
    '',
)

replace_once(
    "tests/test_layout_state_diagram_workspace.py",
    '        "stateDiagramWorkspaceAdaptive",\n',
    '        "stateDiagramWorkspaceAdaptive",\n'
    '        "complexity-2.4)*.46",\n'
    '        "complexity-2.8)*.24",\n',
)

Path(__file__).unlink()

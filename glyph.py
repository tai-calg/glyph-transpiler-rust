#!/usr/bin/env python3
"""One-command Glyph I/O and state-diagram launcher."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from glyph import GlyphError
from glyph.readable_diagram_app import run_diagram_app


DEFAULT_SOURCE = """system DoorControl=control

machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*PanelInput(open_request:B,authorized:B)
*SensorInput(obstruction:B)
*Input(open_request:B,authorized:B,obstruction:B)
+DoorMode=Closed|Opening|Open|Closing|Alarm
*DoorState(mode:DoorMode)

# `ext` is an explicitly declared external component. It is never invented by
# the diagram renderer and is connected through the generated Host boundary.
ext panel():PanelInput
ext sensor():SensorInput
ext actuator(state:DoorState):()

>combine(panel_input:PanelInput,sensor_input:SensorInput):Input=Input(panel_input.open_request,panel_input.authorized,sensor_input.obstruction)

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request&input.authorized >> DoorState(Opening)
  state.mode==Opening&input.obstruction >> DoorState(Alarm)
  state.mode==Opening >> DoorState(Open)
  state.mode==Open&!input.open_request >> DoorState(Closing)
  state.mode==Closing&input.obstruction >> DoorState(Opening)
  state.mode==Closing >> DoorState(Closed)
  _ >> state

# The system graph is derived from these real calls:
# control -> panel / sensor / combine / step / actuator.
>control(state:DoorState):()=actuator(step(state,combine(panel(),sensor())))
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glyph",
        description="Glyphコードを編集・コンパイルし、I/O図と状態遷移図を表示する",
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="開く .glyph ファイル。省略時は .glyph/workspace.glyph を開く",
    )
    return parser


def default_input_path(base: Path | None = None) -> Path:
    root = (base or Path.cwd()).resolve()
    return root / ".glyph" / "workspace.glyph"


def resolve_input(input_path: Path | None) -> Path:
    if input_path is not None:
        return input_path

    path = default_input_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(DEFAULT_SOURCE, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        input_path = resolve_input(args.input)
        if input_path.suffix != ".glyph":
            raise GlyphError("入力ファイルの拡張子は .glyph にする")
        if not input_path.is_file():
            raise GlyphError(f"Glyphファイルが存在しない: {input_path}")
        return run_diagram_app(input_path)
    except (OSError, GlyphError) as exc:
        print(f"glyph: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

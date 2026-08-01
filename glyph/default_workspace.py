from __future__ import annotations

from importlib.resources import files
import os
from pathlib import Path
import sys
from typing import Mapping


APPLICATION_IDENTIFIER = "io.github.tai-calg.glyph-studio"
WORKSPACE_FILENAME = "workspace.glyph"

LEGACY_DEFAULT_SOURCE = """system DoorControl
  panel -> decide
  sensor -> decide
  decide -> lock
  decide -> alarm

machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*Input(open_request:B,authorized:B,obstruction:B)
+DoorMode=Closed|Opening|Open|Closing|Alarm
*DoorState(mode:DoorMode)

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request&input.authorized >> DoorState(Opening)
  state.mode==Opening&input.obstruction >> DoorState(Alarm)
  state.mode==Opening >> DoorState(Open)
  state.mode==Open&!input.open_request >> DoorState(Closing)
  state.mode==Closing&input.obstruction >> DoorState(Opening)
  state.mode==Closing >> DoorState(Closed)
  _ >> state

!lock(state:DoorState):()
!alarm(state:DoorState):()
"""

CODE_DERIVED_DEFAULT_SOURCE = """system DoorControl=control

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

>control(state:DoorState):()=actuator(step(state,combine(panel(),sensor())))
"""

PREVIOUS_CLI_DEFAULT_SOURCE = """system DoorControl
  entry control

  in state:DoorState
  in panel:PanelInput
  in sensor:SensorInput
  out receipt:Receipt

  state -> control
  panel -> control
  sensor -> control
  control -> receipt
  control -> actuator

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
*Receipt(state:DoorState)

# 外部所有の入力はext、外部へ作用する境界は!で宣言する。
ext panel():PanelInput
ext sensor():SensorInput
!actuator(state:DoorState):Receipt

>combine(panel_input:PanelInput,sensor_input:SensorInput):Input=Input(panel_input.open_request,panel_input.authorized,sensor_input.obstruction)

>step(state:DoorState,input:Input):DoorState
  state.mode==Closed&input.open_request&input.authorized >> DoorState(Opening)
  state.mode==Opening&input.obstruction >> DoorState(Alarm)
  state.mode==Opening >> DoorState(Open)
  state.mode==Open&!input.open_request >> DoorState(Closing)
  state.mode==Closing&input.obstruction >> DoorState(Opening)
  state.mode==Closing >> DoorState(Closed)
  _ >> state

# 一回の実行順序は通常関数に置き、systemは境界と主要flowだけを示す。
>control(state:DoorState):Receipt
  input := combine(panel(),sensor())
  next := step(state,input)
  actuator(next)
"""


def load_default_source() -> str:
    return files("glyph").joinpath("resources", "default.glyph").read_text(
        encoding="utf-8"
    )


DEFAULT_SOURCE = load_default_source()
GENERATED_LEGACY_SOURCES = frozenset(
    {
        LEGACY_DEFAULT_SOURCE,
        CODE_DERIVED_DEFAULT_SOURCE,
        PREVIOUS_CLI_DEFAULT_SOURCE,
    }
)


def application_data_directory(
    *,
    home: Path | None = None,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return the same application-data directory used by the Tauri shell."""

    selected_home = (home or Path.home()).expanduser()
    selected_platform = platform or sys.platform
    selected_environ = os.environ if environ is None else environ

    if selected_platform == "darwin":
        root = selected_home / "Library" / "Application Support"
    elif selected_platform.startswith("win"):
        appdata = selected_environ.get("APPDATA")
        root = Path(appdata).expanduser() if appdata else selected_home / "AppData" / "Roaming"
    else:
        xdg_data_home = selected_environ.get("XDG_DATA_HOME")
        root = (
            Path(xdg_data_home).expanduser()
            if xdg_data_home
            else selected_home / ".local" / "share"
        )
    return root / APPLICATION_IDENTIFIER


def default_input_path(data_directory: Path | None = None) -> Path:
    return (data_directory or application_data_directory()) / WORKSPACE_FILENAME


def legacy_input_path(root: Path | None = None) -> Path:
    return (root or Path.cwd()).resolve() / ".glyph" / WORKSPACE_FILENAME


def _canonicalize_generated_sample(source: str) -> str:
    return DEFAULT_SOURCE if source in GENERATED_LEGACY_SOURCES else source


def resolve_input(
    input_path: Path | None,
    *,
    data_directory: Path | None = None,
    legacy_root: Path | None = None,
) -> Path:
    """Resolve one shared Studio workspace without overwriting user edits."""

    if input_path is not None:
        return input_path

    target = default_input_path(data_directory)
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        source = target.read_text(encoding="utf-8")
        migrated = _canonicalize_generated_sample(source)
        if migrated != source:
            target.write_text(migrated, encoding="utf-8")
        return target

    legacy = legacy_input_path(legacy_root)
    if legacy.is_file():
        source = _canonicalize_generated_sample(legacy.read_text(encoding="utf-8"))
    else:
        source = DEFAULT_SOURCE
    target.write_text(source, encoding="utf-8")
    return target


__all__ = [
    "APPLICATION_IDENTIFIER",
    "WORKSPACE_FILENAME",
    "DEFAULT_SOURCE",
    "LEGACY_DEFAULT_SOURCE",
    "CODE_DERIVED_DEFAULT_SOURCE",
    "PREVIOUS_CLI_DEFAULT_SOURCE",
    "GENERATED_LEGACY_SOURCES",
    "application_data_directory",
    "default_input_path",
    "legacy_input_path",
    "load_default_source",
    "resolve_input",
]

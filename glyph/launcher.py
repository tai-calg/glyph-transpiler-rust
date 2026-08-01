from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .compiler import GlyphError
from .default_workspace import (
    CODE_DERIVED_DEFAULT_SOURCE,
    DEFAULT_SOURCE,
    LEGACY_DEFAULT_SOURCE,
    PREVIOUS_CLI_DEFAULT_SOURCE,
    application_data_directory,
    default_input_path,
    legacy_input_path,
    resolve_input,
)
from .desktop_server import run_studio_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glyph",
        description="Glyphコードを編集・コンパイルし、I/O図と状態遷移図を表示する",
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="開く .glyph ファイル。省略時はGlyph Studio共通ワークスペースを開く",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        input_path = resolve_input(args.input)
        if input_path.suffix != ".glyph":
            raise GlyphError("入力ファイルの拡張子は .glyph にする")
        if not input_path.is_file():
            raise GlyphError(f"Glyphファイルが存在しない: {input_path}")
        return run_studio_app(input_path)
    except (OSError, GlyphError, ValueError) as exc:
        print(f"glyph: error: {exc}", file=sys.stderr)
        return 1


__all__ = [
    "CODE_DERIVED_DEFAULT_SOURCE",
    "DEFAULT_SOURCE",
    "LEGACY_DEFAULT_SOURCE",
    "PREVIOUS_CLI_DEFAULT_SOURCE",
    "application_data_directory",
    "build_parser",
    "default_input_path",
    "legacy_input_path",
    "main",
    "resolve_input",
]

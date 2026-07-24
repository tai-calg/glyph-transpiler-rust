#!/usr/bin/env python3
"""One-command Glyph I/O and state-diagram launcher."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from glyph import GlyphError
from glyph.readable_diagram_app import run_diagram_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glyph",
        description="Glyphコードを編集・コンパイルし、I/O図と状態遷移図を表示する",
    )
    parser.add_argument("input", type=Path, help="開く .glyph ファイル")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.input.suffix != ".glyph":
            raise GlyphError("入力ファイルの拡張子は .glyph にする")
        if not args.input.is_file():
            raise GlyphError(f"Glyphファイルが存在しない: {args.input}")
        return run_diagram_app(args.input)
    except (OSError, GlyphError) as exc:
        print(f"glyph: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

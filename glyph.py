#!/usr/bin/env python3
"""One-command Glyph Studio launcher."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from glyph import GlyphError
from glyph.studio import run_studio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glyph",
        description="1つのGlyphファイルを編集・検査・可視化・Rust生成するStudioを起動する",
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
        return run_studio(args.input)
    except (OSError, GlyphError) as exc:
        print(f"glyph: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

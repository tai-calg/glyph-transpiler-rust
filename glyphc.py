#!/usr/bin/env python3
"""Glyph DSLからRustコードを生成する依存ゼロCLI。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from glyph import GlyphError, compile_file, compile_source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glyphc",
        description="頻出概念を短い記号で表すGlyph DSLをRustへ変換する",
    )
    parser.add_argument("input", type=Path, help="入力 .glyph ファイル")
    parser.add_argument("-o", "--output", type=Path, help="出力 .rs ファイル。省略時は標準出力")
    parser.add_argument("--check", action="store_true", help="解析と検査だけを行う")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = args.input.read_text(encoding="utf-8")
        generated = compile_source(source)
        if args.check:
            print(f"OK: {args.input}")
            return 0
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(generated, encoding="utf-8")
            print(f"generated: {args.output}")
        else:
            sys.stdout.write(generated)
        return 0
    except (OSError, GlyphError) as exc:
        print(f"glyphc: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

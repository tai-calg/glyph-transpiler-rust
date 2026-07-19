#!/usr/bin/env python3
"""Glyph DSLからRustコードを生成する依存ゼロCLI。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from glyph import GlyphError, compile_artifacts, compile_source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glyphc",
        description="頻出概念を短い記号で表すGlyph DSLをRustへ変換する",
    )
    parser.add_argument("input", type=Path, help="入力 .glyph ファイル")
    parser.add_argument("-o", "--output", type=Path, help="ロジック側の出力 .rs。省略時は標準出力")
    parser.add_argument(
        "--host-output",
        type=Path,
        help="!境界の試作実装または未接続スタブを出力する .rs",
    )
    parser.add_argument("--check", action="store_true", help="解析と検査だけを行う")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = args.input.read_text(encoding="utf-8")
        artifacts = compile_artifacts(source)
        if args.check:
            print(f"OK: {args.input}")
            return 0
        if args.host_output and not args.output:
            raise GlyphError("--host-output を使う場合は -o/--output も指定する")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(artifacts.logic, encoding="utf-8")
            print(f"generated: {args.output}")
            if args.host_output:
                args.host_output.parent.mkdir(parents=True, exist_ok=True)
                args.host_output.write_text(artifacts.host, encoding="utf-8")
                print(f"generated: {args.host_output}")
        else:
            sys.stdout.write(compile_source(source))
        return 0
    except (OSError, GlyphError) as exc:
        print(f"glyphc: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

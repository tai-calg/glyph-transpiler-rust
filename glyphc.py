#!/usr/bin/env python3
"""Glyph DSL compiler, semantic inspector, REPL, and live diagram watcher."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from glyph import GlyphError
from glyph.compilation import CompilationPipeline
from glyph.incremental import IncrementalCompiler, watch_file
from glyph.repl import run_repl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glyphc",
        description="Glyph DSLをRust、型付きAST、実行構造図へ変換する",
    )
    parser.add_argument("input", type=Path, help="入力 .glyph ファイル")
    parser.add_argument("-o", "--output", type=Path, help="ロジック側の出力 .rs")
    parser.add_argument(
        "--host-output",
        type=Path,
        help="!境界の試作実装または未接続スタブを出力する .rs",
    )
    parser.add_argument(
        "--diagram-dir",
        type=Path,
        help="実行構造IR、Mermaid図、source mapを出力するディレクトリ",
    )
    parser.add_argument(
        "--ast-json",
        type=Path,
        help="SymbolId、:=ブロック、ラムダ、Architectureを含む型付き設計JSONを出力する",
    )
    parser.add_argument("--check", action="store_true", help="解析と検査だけを行う")
    parser.add_argument("--repl", action="store_true", help="開発時REPLを起動する")
    parser.add_argument("--watch", action="store_true", help="変更を監視して増分再生成する")
    parser.add_argument(
        "--watch-once",
        action="store_true",
        help="watch処理を1回だけ実行する。CIとスクリプト向け",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="watch間隔。最小0.1秒、既定0.5秒",
    )
    return parser


def _source_href(input_path: Path, diagram_dir: Path | None) -> str | None:
    if diagram_dir is None:
        return None
    return os.path.relpath(input_path, diagram_dir).replace(os.sep, "/")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.host_output and not args.output:
            raise GlyphError("--host-output を使う場合は -o/--output も指定する")
        if args.repl and (args.watch or args.watch_once or args.check):
            raise GlyphError("--repl は --watch/--watch-once/--check と同時に使えない")

        if args.repl:
            return run_repl(args.input, args.diagram_dir, stdin=sys.stdin, stdout=sys.stdout)

        if args.watch or args.watch_once:
            diagram_dir = args.diagram_dir or (args.input.parent / ".glyph" / args.input.stem)
            compiler = IncrementalCompiler()

            def report(result) -> None:
                if not result.changed:
                    return
                print(f"compiled: {args.input} [{result.snapshot.digest[:12]}]")
                for path in result.written:
                    print(f"generated: {path}")

            watch_file(
                compiler,
                args.input,
                logic_output=args.output,
                host_output=args.host_output,
                diagram_dir=diagram_dir,
                ast_output=args.ast_json,
                interval=args.interval,
                once=args.watch_once,
                on_result=report,
            )
            return 0

        source = args.input.read_text(encoding="utf-8")
        outputs = CompilationPipeline().compile_text(
            source,
            str(args.input),
            _source_href(args.input, args.diagram_dir),
        )
        artifacts = outputs.artifacts

        if args.check:
            print(f"OK: {args.input}")
            return 0

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(artifacts.logic, encoding="utf-8")
            print(f"generated: {args.output}")
            if args.host_output:
                args.host_output.parent.mkdir(parents=True, exist_ok=True)
                args.host_output.write_text(artifacts.host, encoding="utf-8")
                print(f"generated: {args.host_output}")

        if args.diagram_dir:
            args.diagram_dir.mkdir(parents=True, exist_ok=True)
            for name, content in outputs.diagrams.files.items():
                path = args.diagram_dir / name
                path.write_text(content, encoding="utf-8")
            for name in sorted(outputs.diagrams.files):
                print(f"generated: {args.diagram_dir / name}")

        if args.ast_json:
            args.ast_json.parent.mkdir(parents=True, exist_ok=True)
            args.ast_json.write_text(outputs.design_json, encoding="utf-8")
            print(f"generated: {args.ast_json}")

        if not args.output and not args.diagram_dir and not args.ast_json:
            sys.stdout.write(artifacts.logic)
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, GlyphError) as exc:
        print(f"glyphc: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

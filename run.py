#!/usr/bin/env python3
"""サンプルの再生成・検査・実行を一括で行う。"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from glyph import GlyphError, compile_file

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "examples" / "controller.glyph"
GENERATED = ROOT / "demo" / "src" / "generated.rs"


def main() -> int:
    try:
        compile_file(SOURCE, GENERATED)
    except (OSError, GlyphError) as exc:
        print(f"生成失敗: {exc}", file=sys.stderr)
        return 1

    print(f"生成完了: {GENERATED.relative_to(ROOT)}")

    cargo = shutil.which("cargo")
    if cargo is None:
        print("cargoが見つからないため、Rustのビルドだけを省略した。")
        print("Rust導入後に `python3 run.py` を再実行する。")
        return 0

    subprocess.run(
        [cargo, "test", "--manifest-path", str(ROOT / "demo" / "Cargo.toml")],
        check=True,
    )
    subprocess.run(
        [cargo, "run", "--quiet", "--manifest-path", str(ROOT / "demo" / "Cargo.toml")],
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

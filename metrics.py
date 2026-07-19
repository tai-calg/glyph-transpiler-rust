#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def metrics(path: Path, comment_prefixes: tuple[str, ...]) -> tuple[int, int, int]:
    text = path.read_text(encoding="utf-8")
    lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(comment_prefixes)
    ]
    joined = "\n".join(lines)
    compact = "".join(joined.split())
    return len(lines), len(joined), len(compact)


for relative, prefixes in [
    ("examples/controller.glyph", ("#",)),
    ("demo/src/generated.rs", ("//", "#!")),
]:
    line_count, chars, compact = metrics(ROOT / relative, prefixes)
    print(f"{relative}: code_lines={line_count}, chars={chars}, compact_chars={compact}")

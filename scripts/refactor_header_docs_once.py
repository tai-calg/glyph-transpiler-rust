from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SELF = ROOT / "scripts" / "refactor_header_docs_once.py"
WORKFLOW = ROOT / ".github" / "workflows" / "refactor-header-docs-once.yml"
TRIGGER = ROOT / ".refactor-header-docs-trigger"

GLYPH_FENCE_RE = re.compile(r"```glyph\n(?P<body>.*?)```", re.DOTALL)
INLINE_LINK_RE = re.compile(
    r"(?P<prefix>!?\[[^\]]*\]\()"
    r"(?P<dest>[^)\s]+)"
    r"(?P<suffix>(?:\s+[\"'][^\"']*[\"'])?\))"
)
REFERENCE_LINK_RE = re.compile(
    r"(?m)^(?P<prefix>\s*\[[^\]]+\]:\s*)(?P<dest>\S+)"
)


def _top_level_blocks(source: str) -> tuple[list[str], list[str], list[str]]:
    """Split Glyph source into system headers, machine headers, and the body."""

    lines = source.splitlines()
    systems: list[str] = []
    machines: list[str] = []
    body: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.split("#", 1)[0].rstrip()
        is_header = (
            stripped.startswith("system ") or stripped.startswith("machine ")
        ) and not line[:1].isspace()
        if not is_header:
            body.append(line)
            index += 1
            continue

        block = [line]
        index += 1
        while index < len(lines):
            candidate = lines[index]
            clean = candidate.split("#", 1)[0].rstrip()
            if clean and not candidate[:1].isspace():
                break
            block.append(candidate)
            index += 1

        while block and not block[-1].strip():
            block.pop()
        rendered = "\n".join(block)
        if stripped.startswith("system "):
            systems.append(rendered)
        else:
            machines.append(rendered)

    return systems, machines, body


def reorder_glyph_headers(source: str) -> str:
    """Make system/machine declarations a file-leading design header."""

    systems, machines, body = _top_level_blocks(source)
    if not systems and not machines:
        return source

    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()

    sections: list[str] = []
    if systems:
        sections.append("\n\n".join(systems))
    if machines:
        sections.append("\n\n".join(machines))
    if body:
        sections.append("\n".join(body))

    result = "\n\n".join(sections)
    if source.endswith("\n"):
        result += "\n"
    return result


def rewrite_glyph_fences(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        body = match.group("body")
        return "```glyph\n" + reorder_glyph_headers(body) + "```"

    return GLYPH_FENCE_RE.sub(replace, text)


def split_suffix(target: str) -> tuple[str, str]:
    positions = [pos for marker in ("#", "?") if (pos := target.find(marker)) >= 0]
    if not positions:
        return target, ""
    pos = min(positions)
    return target[:pos], target[pos:]


def moved_doc_target(target: str, moved_names: set[str]) -> str:
    wrapped = target.startswith("<") and target.endswith(">")
    raw = target[1:-1] if wrapped else target
    if raw.startswith(("#", "/", "http://", "https://", "mailto:", "data:")):
        return target

    path, suffix = split_suffix(raw)
    normalized = path[2:] if path.startswith("./") else path
    if normalized in moved_names:
        rewritten = normalized
    elif normalized == "README.md":
        rewritten = "../README.md"
    elif path.startswith("../"):
        rewritten = path
    elif path:
        rewritten = "../" + path
    else:
        rewritten = path
    result = rewritten + suffix
    return f"<{result}>" if wrapped else result


def rewrite_moved_doc_links(text: str, moved_names: set[str]) -> str:
    def inline(match: re.Match[str]) -> str:
        return (
            match.group("prefix")
            + moved_doc_target(match.group("dest"), moved_names)
            + match.group("suffix")
        )

    def reference(match: re.Match[str]) -> str:
        return match.group("prefix") + moved_doc_target(
            match.group("dest"), moved_names
        )

    return REFERENCE_LINK_RE.sub(reference, INLINE_LINK_RE.sub(inline, text))


def rewrite_root_doc_references(text: str, moved_names: set[str]) -> str:
    for name in sorted(moved_names, key=len, reverse=True):
        text = text.replace(f"./{name}", f"./docs/{name}")
        text = re.sub(
            rf"(?<!docs/)(?<![A-Za-z0-9_./-]){re.escape(name)}",
            f"docs/{name}",
            text,
        )
    return text


def is_probably_text(path: Path) -> bool:
    if path.name in {"Makefile", ".gitignore"}:
        return True
    return path.suffix in {
        ".md",
        ".py",
        ".yml",
        ".yaml",
        ".toml",
        ".txt",
        ".rs",
        ".glyph",
        ".json",
        ".html",
        ".css",
        ".js",
    }


def update_source_contract() -> None:
    architecture = ROOT / "glyph" / "architecture.py"
    text = architecture.read_text(encoding="utf-8")
    text = text.replace(
        '    """Extract `system Name` blocks and preserve all source line numbers."""',
        '    """Extract file-leading `system Name` headers.\n\n'
        '    Component names are bound only after the complete Program is parsed, so a\n'
        '    header may reference declarations written later in the same file. Legacy\n'
        '    tail placement remains accepted for source compatibility.\n'
        '    """',
    )
    architecture.write_text(text, encoding="utf-8")

    machine = ROOT / "glyph" / "machine.py"
    text = machine.read_text(encoding="utf-8")
    text = text.replace(
        '    """`machine Name(params)`ブロックを抽出し、元の行番号を保つ空行へ置換する。"""',
        '    """ファイル先頭の`machine Name(params)`ヘッダを抽出する。\n\n'
        '    状態型とnext関数は全宣言のparse後に検証するため、ヘッダから後続\n'
        '    宣言へのforward bindingを許可する。旧来の末尾配置も互換受理する。\n'
        '    """',
    )
    machine.write_text(text, encoding="utf-8")


def add_header_layout_tests() -> None:
    path = ROOT / "tests" / "test_header_first_layout.py"
    path.write_text(
        '''from __future__ import annotations

from pathlib import Path
import unittest

from glyph import compile_artifacts, parse_compilation_model


HEADER_FIRST = """\
system MotorSafety
  sensor -> decide
  decide -> step
  step -> write_motor

machine Motor(state:MotorState,input:Input)
  select=state.mode
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted

+Mode=Stopped|Running|Faulted
+Command=Stop|Drive(U)
*Input(raw:U)
*MotorState(mode:Mode,command:Command)
*Receipt(command:Command)

>decide(input:Input):Command
  input.raw==0 >> Stop
  _ >> Drive(input.raw)

>step(state:MotorState,input:Input):MotorState
  command := decide(input)
  command==Stop >> MotorState(Stopped,Stop)
  command==Drive(speed) >> MotorState(Running,Drive(speed))
  _ >> MotorState(Faulted,Stop)

!write_motor(command:Command):Receipt
"""

LEGACY_TAIL = """\
+Mode=Stopped|Running|Faulted
+Command=Stop|Drive(U)
*Input(raw:U)
*MotorState(mode:Mode,command:Command)
*Receipt(command:Command)

>decide(input:Input):Command
  input.raw==0 >> Stop
  _ >> Drive(input.raw)

>step(state:MotorState,input:Input):MotorState
  command := decide(input)
  command==Stop >> MotorState(Stopped,Stop)
  command==Drive(speed) >> MotorState(Running,Drive(speed))
  _ >> MotorState(Faulted,Stop)

!write_motor(command:Command):Receipt

system MotorSafety
  sensor -> decide
  decide -> step
  step -> write_motor

machine Motor(state:MotorState,input:Input)
  select=state.mode
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted
"""


class HeaderFirstLayoutTests(unittest.TestCase):
    def test_system_and_machine_headers_forward_bind(self) -> None:
        model = parse_compilation_model(HEADER_FIRST, "motor.glyph")
        self.assertEqual([system.name for system in model.systems], ["MotorSafety"])
        self.assertEqual([machine.name for machine in model.machines], ["Motor"])
        components = {
            component.name: component.kind
            for component in model.architecture.systems[0].components
        }
        self.assertEqual(components["sensor"], "external")
        self.assertEqual(components["decide"], "function")
        self.assertEqual(components["step"], "function")
        self.assertEqual(components["write_motor"], "effect")

    def test_legacy_tail_placement_remains_compatible(self) -> None:
        header = compile_artifacts(HEADER_FIRST)
        legacy = compile_artifacts(LEGACY_TAIL)
        self.assertEqual(header.logic, legacy.logic)
        self.assertEqual(header.host, legacy.host)

    def test_official_examples_keep_headers_before_body(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for path in sorted((root / "examples").rglob("*.glyph")):
            lines = path.read_text(encoding="utf-8").splitlines()
            body_seen = False
            for line_no, original in enumerate(lines, start=1):
                clean = original.split("#", 1)[0].rstrip()
                if not clean or original[:1].isspace():
                    continue
                if clean.startswith(("system ", "machine ")):
                    self.assertFalse(
                        body_seen,
                        f"{path}:{line_no}: design header must precede declarations",
                    )
                elif not clean.startswith("@"):
                    body_seen = True

    def test_repository_root_contains_only_readme_markdown(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(
            {path.name for path in root.glob("*.md")},
            {"README.md"},
        )
        self.assertTrue((root / "docs" / "README.md").is_file())


if __name__ == "__main__":
    unittest.main()
''',
        encoding="utf-8",
    )


def insert_readme_header_section() -> None:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    marker = "## 全体例\n"
    section = '''## ファイル先頭の設計ヘッダ

`system`と`machine`は、宣言本体を包むブロックではなく、ファイル全体の設計を先に示すヘッダです。正規形では、ファイル先頭に`system`、続けて`machine`を書き、その後に型・純粋関数・作用境界を記述します。

```glyph
system MotorSafety
  sensor -> decide
  decide -> step
  step -> write_motor

machine Motor(state:MotorState,input:Input)
  select=state.mode
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted

# 以降に型・関数・作用境界を宣言する
```

component、状態型、`next`関数はファイル全体を解析した後に名前解決するため、ヘッダから後続宣言へのforward bindingが可能です。既存sourceとの互換性のため末尾配置も受理しますが、README・examples・新規コードは先頭配置へ統一します。

'''
    if "## ファイル先頭の設計ヘッダ" not in text:
        text = text.replace(marker, section + marker, 1)
    path.write_text(text, encoding="utf-8")


def move_documents() -> set[str]:
    DOCS.mkdir(exist_ok=True)
    root_docs = sorted(
        path for path in ROOT.glob("*.md") if path.name != "README.md"
    )
    moved_names = {path.name for path in root_docs}

    for source in root_docs:
        text = rewrite_glyph_fences(source.read_text(encoding="utf-8"))
        text = rewrite_moved_doc_links(text, moved_names)
        destination = DOCS / source.name
        destination.write_text(text, encoding="utf-8")
        source.unlink()

    return moved_names


def create_docs_index(moved_names: set[str]) -> None:
    entries: list[tuple[str, str]] = []
    for name in sorted(moved_names):
        path = DOCS / name
        title = name
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        entries.append((name, title))

    content = [
        "# Documentation",
        "",
        "Glyphの詳細文書をこのディレクトリへ集約しています。入口はルートの[README](../README.md)です。",
        "",
    ]
    for name, title in entries:
        content.append(f"- [{title}]({name})")
    content.append("")
    (DOCS / "README.md").write_text("\n".join(content), encoding="utf-8")


def rewrite_repository_references(moved_names: set[str]) -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.parent == DOCS and path.suffix == ".md":
            continue
        if path in {SELF, WORKFLOW, TRIGGER} or not is_probably_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = rewrite_root_doc_references(text, moved_names)
        if path.suffix == ".md":
            updated = rewrite_glyph_fences(updated)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def reorder_examples() -> None:
    for path in sorted((ROOT / "examples").rglob("*.glyph")):
        original = path.read_text(encoding="utf-8")
        updated = reorder_glyph_headers(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")


def update_checksums() -> None:
    path = ROOT / "CHECKSUMS.txt"
    if not path.exists():
        return

    output: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            output.append(line)
            continue
        _, relative = parts
        candidate = ROOT / relative.removeprefix("./")
        if not candidate.exists() and candidate.suffix == ".md":
            candidate = DOCS / candidate.name
            relative = f"./docs/{candidate.name}"
        if not candidate.is_file():
            output.append(line)
            continue
        digest = sha256(candidate.read_bytes()).hexdigest()
        output.append(f"{digest}  {relative}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def cleanup_one_shot_files() -> None:
    for path in (SELF, WORKFLOW, TRIGGER):
        if path.exists():
            path.unlink()


def main() -> None:
    reorder_examples()

    for path in sorted(ROOT.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        updated = rewrite_glyph_fences(text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")

    update_source_contract()
    add_header_layout_tests()
    insert_readme_header_section()

    moved_names = move_documents()
    create_docs_index(moved_names)
    rewrite_repository_references(moved_names)
    update_checksums()
    cleanup_one_shot_files()


if __name__ == "__main__":
    main()

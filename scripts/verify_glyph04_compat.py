from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from glyph.schema import COMPATIBILITY_REPORT_SCHEMA, IR_SCHEMA_VERSION  # noqa: E402


LEGACY_SOURCES = (
    "examples/acceptance/door_controller.glyph",
    "examples/acceptance/job_scheduler.glyph",
    "examples/acceptance/motor_safety.glyph",
    "examples/controller.glyph",
    "examples/system_controller.glyph",
    "examples/lisp_core.glyph",
    "examples/door_sketch.glyph",
    "examples/algorithm_sketch.glyph",
)

INVALID_LEGACY_SOURCES = {
    "unclosed-product": "*Point(x:I\n",
    "empty-function-body": ">bad(x:I):I=\n",
    "duplicate-macro": "@X=1\n@X=2\n>same(x:I):I=x\n",
}


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _compile(
    compiler_root: Path,
    source: Path,
    destination: Path,
) -> subprocess.CompletedProcess[str]:
    destination.mkdir(parents=True, exist_ok=True)
    return _run(
        [
            sys.executable,
            str(compiler_root / "glyphc.py"),
            str(source),
            "-o",
            str(destination / "generated.rs"),
            "--host-output",
            str(destination / "host.generated.rs"),
            "--diagram-dir",
            str(destination / "diagrams"),
            "--ast-json",
            str(destination / "typed-design.json"),
        ],
        compiler_root,
    )


def _files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)).replace(os.sep, "/"): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _normalize(text: str, replacements: tuple[tuple[str, str], ...]) -> str:
    normalized = text.replace("\r\n", "\n")
    for source, target in replacements:
        normalized = normalized.replace(source, target)
    return normalized


def _compare_source(
    source: Path,
    base_root: Path,
    temporary: Path,
) -> tuple[dict[str, object], list[str]]:
    slug = source.stem
    base_output = temporary / "outputs" / "base" / slug
    head_output = temporary / "outputs" / "head" / slug
    base = _compile(base_root, source, base_output)
    head = _compile(ROOT, source, head_output)
    errors: list[str] = []
    if base.returncode != 0:
        errors.append(f"main compiler failed for {source}: {base.stderr}")
    if head.returncode != 0:
        errors.append(f"Glyph 0.4 compiler failed for {source}: {head.stderr}")

    base_files = _files(base_output) if base.returncode == 0 else {}
    head_files = _files(head_output) if head.returncode == 0 else {}
    base_names = set(base_files)
    head_names = set(head_files)
    if base_names != head_names:
        errors.append(
            f"{source}: artifact set differs; "
            f"main-only={sorted(base_names - head_names)}, "
            f"head-only={sorted(head_names - base_names)}"
        )
    changed = [
        name
        for name in sorted(base_names & head_names)
        if base_files[name] != head_files[name]
    ]
    if changed:
        errors.append(f"{source}: byte differences in {changed}")
    return {
        "source": str(source.relative_to(ROOT)),
        "main_exit": base.returncode,
        "head_exit": head.returncode,
        "files": sorted(head_names),
        "byte_equal": not changed and base_names == head_names,
    }, errors


def _compare_diagnostics(
    base_root: Path,
    temporary: Path,
) -> tuple[list[dict[str, object]], list[str]]:
    results: list[dict[str, object]] = []
    errors: list[str] = []
    invalid_root = temporary / "invalid"
    invalid_root.mkdir(parents=True, exist_ok=True)
    replacements = (
        (str(base_root), "<base>"),
        (str(ROOT), "<repo>"),
        (str(temporary), "<tmp>"),
    )
    for name, source in INVALID_LEGACY_SOURCES.items():
        path = invalid_root / f"{name}.glyph"
        path.write_text(source, encoding="utf-8")
        base = _run(
            [sys.executable, str(base_root / "glyphc.py"), str(path), "--check"],
            base_root,
        )
        head = _run(
            [sys.executable, str(ROOT / "glyphc.py"), str(path), "--check"],
            ROOT,
        )
        base_stdout = _normalize(base.stdout, replacements)
        head_stdout = _normalize(head.stdout, replacements)
        base_stderr = _normalize(base.stderr, replacements)
        head_stderr = _normalize(head.stderr, replacements)
        equal = (
            base.returncode == head.returncode
            and base_stdout == head_stdout
            and base_stderr == head_stderr
        )
        if not equal:
            errors.append(
                f"diagnostic case {name!r} differs: "
                f"main=({base.returncode}, {base_stdout!r}, {base_stderr!r}), "
                f"head=({head.returncode}, {head_stdout!r}, {head_stderr!r})"
            )
        results.append(
            {
                "case": name,
                "main_exit": base.returncode,
                "head_exit": head.returncode,
                "stdout_equal": base_stdout == head_stdout,
                "stderr_equal": base_stderr == head_stderr,
            }
        )
    return results, errors


def build_compatibility_report(base_ref: str) -> dict[str, object]:
    errors: list[str] = []
    source_results: list[dict[str, object]] = []
    diagnostic_results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="glyph04-compat-") as directory:
        temporary = Path(directory)
        base_root = temporary / "main"
        added = _run(
            ["git", "worktree", "add", "--detach", str(base_root), base_ref],
            ROOT,
        )
        if added.returncode != 0:
            errors.append(f"cannot create {base_ref} worktree: {added.stderr}")
        else:
            try:
                for relative in LEGACY_SOURCES:
                    source = ROOT / relative
                    if not source.is_file():
                        errors.append(f"legacy compatibility source is missing: {relative}")
                        continue
                    result, case_errors = _compare_source(
                        source,
                        base_root,
                        temporary,
                    )
                    source_results.append(result)
                    errors.extend(case_errors)
                diagnostic_results, diagnostic_errors = _compare_diagnostics(
                    base_root,
                    temporary,
                )
                errors.extend(diagnostic_errors)
            finally:
                removed = _run(
                    ["git", "worktree", "remove", "--force", str(base_root)],
                    ROOT,
                )
                if removed.returncode != 0:
                    shutil.rmtree(base_root, ignore_errors=True)
                    errors.append(f"cannot remove compatibility worktree: {removed.stderr}")

    return {
        "schema": COMPATIBILITY_REPORT_SCHEMA,
        "version": IR_SCHEMA_VERSION,
        "status": "passed" if not errors else "failed",
        "base_ref": base_ref,
        "legacy_sources": source_results,
        "diagnostics": diagnostic_results,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare legacy Glyph behavior against the main branch"
    )
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build" / "glyph04-compatibility.json",
    )
    args = parser.parse_args()

    report = build_compatibility_report(args.base_ref)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if report["status"] != "passed":
        for error in report["errors"]:
            print(f"glyph04-compatibility: {error}", file=sys.stderr)
        return 1
    print(
        f"Glyph 0.4 compatibility passed: {len(report['legacy_sources'])} legacy "
        f"sources and {len(report['diagnostics'])} diagnostics"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

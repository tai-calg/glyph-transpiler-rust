from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
DESKTOP = ROOT / "desktop"
TAURI = DESKTOP / "src-tauri"
BINARIES = TAURI / "binaries"
ENTRY = DESKTOP / "sidecar_entry.py"


def target_triple() -> str:
    explicit = os.environ.get("TAURI_ENV_TARGET_TRIPLE")
    if explicit:
        return explicit
    result = subprocess.run(
        ["rustc", "-vV"],
        check=True,
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("host: "):
            return line.removeprefix("host: ").strip()
    raise RuntimeError("rustc did not report a host target triple")


def destination(triple: str) -> Path:
    suffix = ".exe" if "windows" in triple else ""
    return BINARIES / f"glyph-studio-server-{triple}{suffix}"


def make_placeholder(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".exe":
        path.write_bytes(b"")
    else:
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def build(path: Path, *, development: bool) -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "PyInstaller is required. Install the desktop dependencies with "
            "`python -m pip install -e '.[desktop]'`."
        ) from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="glyph-sidecar-") as directory:
        temp = Path(directory)
        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--onefile",
            "--name",
            "glyph-studio-server",
            "--distpath",
            str(temp / "dist"),
            "--workpath",
            str(temp / "work"),
            "--specpath",
            str(temp / "spec"),
            "--paths",
            str(ROOT),
            "--collect-data",
            "glyph",
        ]
        if not development:
            command.append("--clean")
        command.append(str(ENTRY))
        subprocess.run(command, cwd=ROOT, check=True)
        built = temp / "dist" / ("glyph-studio-server.exe" if os.name == "nt" else "glyph-studio-server")
        shutil.copy2(built, path)
        if path.suffix != ".exe":
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the target-specific Glyph Tauri sidecar")
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--placeholder", action="store_true")
    args = parser.parse_args()

    triple = target_triple()
    output = destination(triple)
    if args.placeholder:
        make_placeholder(output)
    else:
        build(output, development=args.development)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

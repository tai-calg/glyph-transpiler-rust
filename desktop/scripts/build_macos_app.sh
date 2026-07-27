#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHON="${GLYPH_PYTHON:-$ROOT/.venv/bin/python3}"
BIN_DIR="$ROOT/desktop/src-tauri/binaries"
APP="$ROOT/desktop/src-tauri/target/release/bundle/macos/Glyph Studio.app"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "error: macOSで実行してください" >&2
  exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "error: Pythonがありません: $PYTHON" >&2
  exit 1
fi

for command_name in arch file npm rustc; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "error: 必要なコマンドがありません: $command_name" >&2
    exit 1
  fi
done

echo "==> Glyph Studio macOS dual-sidecar build"
echo "==> Repository: $ROOT"
echo "==> Python:     $PYTHON"

echo "==> Installing Python dependencies"
"$PYTHON" -m pip install -e '.[desktop]'

echo "==> Installing npm dependencies"
npm install --prefix desktop

rm -rf "$BIN_DIR"
mkdir -p "$BIN_DIR"

build_sidecar() {
  local arch_flag="$1"
  local triple="$2"
  local expected_arch="$3"
  local output="$BIN_DIR/glyph-studio-server-$triple"

  echo
  echo "==> Building sidecar: $triple"

  TAURI_ENV_TARGET_TRIPLE="$triple" \
    arch "$arch_flag" "$PYTHON" desktop/scripts/build_sidecar.py

  if [[ ! -x "$output" ]]; then
    echo "error: sidecarが生成されませんでした: $output" >&2
    exit 1
  fi

  local info
  info="$(file "$output")"
  echo "==> $info"

  if [[ "$info" != *"$expected_arch"* ]]; then
    echo "error: sidecarの実アーキテクチャが不正です" >&2
    exit 1
  fi
}

# Tauri CLIがarm64でもx86_64でも動作できるよう、両方を作る。
build_sidecar -arm64  aarch64-apple-darwin arm64
build_sidecar -x86_64 x86_64-apple-darwin x86_64

echo
echo "==> Generated sidecars"
ls -lah "$BIN_DIR"

test -x "$BIN_DIR/glyph-studio-server-aarch64-apple-darwin"
test -x "$BIN_DIR/glyph-studio-server-x86_64-apple-darwin"

echo
echo "==> Removing previous bundle"
rm -rf "$ROOT/desktop/src-tauri/target/release/bundle"

echo "==> Generating application icons"
npm run --prefix desktop icons

echo "==> Building Glyph Studio.app"
npm run --prefix desktop tauri -- build

if [[ ! -d "$APP" ]]; then
  APP="$(find "$ROOT/desktop/src-tauri/target" \
    -type d -name 'Glyph Studio.app' -print -quit)"
fi

if [[ -z "$APP" || ! -d "$APP" ]]; then
  echo "error: Glyph Studio.appが生成されませんでした" >&2
  exit 1
fi

echo
echo "========================================"
echo "Build succeeded"
echo "App: $APP"
echo "========================================"

if [[ "${1:-}" == "--open" ]]; then
  open "$APP"
fi

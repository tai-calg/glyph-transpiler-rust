# Glyph Studio Desktop

Tauri 2でGlyph Diagram Appをデスクトップアプリとして配布する層です。Python compilerをRustへ複製せず、既存のcompiler-backed UIをloopback sidecarとして再利用します。

## 構成

```text
trusted Vite/Tauri shell
  ├── Open Glyph… native dialog
  ├── sidecar lifecycle
  └── sandboxed iframe
        ↓ authenticated loopback URL
Glyph Python sidecar
  ├── IncrementalCompiler
  ├── editor/save/preview API
  └── State / I/O / Architecture views
```

境界規則:

- Tauri commandを呼べるのはbundle済み親画面だけ
- Glyph UIはsandbox付きiframe内
- sidecarは`127.0.0.1`のrandom portだけでlisten
- launch URLに256-bit相当のsession tokenを含め、HttpOnly cookieへ交換
- APIはsession cookieがなければ`403`
- WebViewへshell plugin permissionや任意filesystem permissionを公開しない
- app終了、source切替、engine restart時に旧sidecarをkillする

## 開発起動

必要条件:

- Python 3.10+
- Rust 1.77.2+
- Node.js 20.19+または22+
- Tauri 2のOS別system dependencies

```bash
python3 -m pip install -e '.[desktop]'
cd desktop
npm install
npm run dev
```

`npm run dev`は現在のtarget triple向けにPyInstaller sidecarを作成してから`tauri dev`を起動します。初回buildは依存取得を含むため時間がかかります。

## 製品build

```bash
python3 -m pip install -e '.[desktop]'
cd desktop
npm install
npm run build
```

生成物は`desktop/src-tauri/target/release/bundle/`以下です。OSごとにそのOS上でbuildします。

## コマンド

| command | 内容 |
|---|---|
| `npm run dev` | sidecarを作りTauri開発起動 |
| `npm run build` | sidecarを同梱したinstallerを作成 |
| `npm run build:web` | trusted frontendだけをbundle |
| `npm run check` | placeholder sidecar、Vite build、`cargo check` |
| `python3 -m glyph.desktop_server --source file.glyph` | sidecar単体診断 |

## ファイル所有権

- `ui/`: trusted Tauri parent frontend
- `src-tauri/`: window、native dialog、sidecar lifecycle
- `scripts/build_sidecar.py`: target-specific sidecar生成
- `resources/default.glyph`: 初回workspaceのtemplate
- `glyph/desktop_server.py`: authenticated loopback adapter

compiler、diagram semantics、editor renderingをdesktop層へ再実装しません。desktopはprocess境界とOS integrationだけを所有します。

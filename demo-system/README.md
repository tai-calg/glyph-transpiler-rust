# Glyph system controller demo

`examples/system_controller.glyph`から制御ロジックと時相モニタを含む`generated.rs`を生成し、privateなHost adapterとpublic facadeを通して実行するE2E例である。

## 生成と実行

```bash
python3 glyphc.py examples/system_controller.glyph \
  -o demo-system/src/generated.rs \
  --host-output demo-system/src/host.generated.rs
cargo test --manifest-path demo-system/Cargo.toml
cargo run --manifest-path demo-system/Cargo.toml
```

## 依存方向

```text
public caller
    ↓
lib.rs selective facade
    ↓
controller.rs
    ├── generated.rs
    └── host.rs
```

- `src/lib.rs`: `Controller`、`Input`、enum、immutable snapshotだけを再公開する
- `src/controller.rs`: 時刻供給、モニタ統合、違反時の安全側復旧
- `src/generated.rs`: Glyphから生成したRustロジックとモニタ。module自体はprivate
- `src/host.rs`: デモ用の手書き作用境界実装。関数はcrate-private
- `src/host.generated.rs`: 未接続作用境界の生成stub。実機接続時のAPI基準
- `src/tests.rs`: Host call log、故障注入を使うcrate内unit test

`controller`、`generated`、`host`を`pub mod`として公開しない。生成された`System`、`Cycle`、`Receipt`もそのまま再公開せず、`SystemSnapshot`と`ReceiptSnapshot`のprivate fieldをread-only accessor経由で参照する。`MonitorSnapshot`と`StepOutcome`のfieldもprivateである。数値違反codeは`ViolationCode`へ型付けし、wire値への変換はcrate内に閉じる。

## GlyphとHostの責務

`system_controller.glyph`が所有するもの:

- System Contextとtyped port
- 型、検証、制御判断
- 状態遷移
- 作用境界宣言
- 時相制約

Rust Hostが所有するもの:

- 時計取得と周期実行
- GPIO/CAN/PWMなど具体I/O
- 作用完了の確認とReceipt生成
- 違反通知
- timeout、故障注入、復旧

時計、scheduler、device driverをGlyphへ埋め込まず、型付き境界の外側へ残す。

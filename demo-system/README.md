# Glyph system controller demo

`examples/system_controller.glyph`から、制御ロジックと時相モニタを含む`generated.rs`、および未接続の作用境界stubを生成し、手書きホスト層と接続するE2E例である。

## 生成と実行

```bash
python3 glyphc.py examples/system_controller.glyph \
  -o demo-system/src/generated.rs \
  --host-output demo-system/src/host.generated.rs
cargo test --manifest-path demo-system/Cargo.toml
cargo run --manifest-path demo-system/Cargo.toml
```

## 責務分離

- `system_controller.glyph`: 型、検証、制御判断、状態遷移、作用境界宣言、時相制約
- `src/generated.rs`: Glyphから生成したRustロジックと参照・逐次モニタ
- `src/host.generated.rs`: 未接続作用境界の生成stub。実機接続時のAPI基準
- `src/host.rs`: デモ用の手書き作用境界実装
- `src/controller.rs`: 単調時刻の供給、モニタ統合、違反時の安全側復旧
- `tests/system_controller.rs`: 正常、低電圧、高温、未認可、緊急停止、ACK timeout、heartbeat断、fault閉状態を検証

時計取得、周期実行、デバイスI/O、違反後の復旧はGlyphへ埋め込まず、Rustホスト側に残している。

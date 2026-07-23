# 検証記録

実施日: 2026-07-19  
実施環境: ChatGPT container, Python 3.13.5

## 実施済み

```bash
python3 -m unittest discover -s tests -v
```

結果:

- Pythonテスト: 20件成功
- Rustデモテスト: 1件はCargo不在のためスキップ
- 失敗: 0件

単語マクロについて検証した項目:

1. 数値マクロの展開
2. 完全一致する識別子だけの置換
3. 式マクロの括弧化による演算子優先順位保存
4. 関数名エイリアス
5. 入れ子マクロ
6. 重複定義の拒否
7. 直接・間接循環の拒否
8. 未使用でも不正なマクロ本体の拒否
9. 宣言名との衝突拒否
10. 同一入力から同一Rustを生成する決定性

```bash
python3 run.py
```

結果:

- `examples/controller.glyph`の解析成功
- 6個の単語マクロの展開成功
- `demo/src/generated.rs`の生成成功
- Cargo不在を検出し、Rustビルドのみ省略

```bash
python3 metrics.py
```

結果:

```text
examples/controller.glyph: code_lines=18, chars=389, compact_chars=356
demo/src/generated.rs: code_lines=39, chars=771, compact_chars=544
```

## Rust環境で実行される検査

Cargoが存在する環境では、`python3 run.py`が次を自動実行する。

```bash
cargo test --manifest-path demo/Cargo.toml
cargo run --quiet --manifest-path demo/Cargo.toml
```

Rust側には以下の4テストを収録している。

1. 通常要求が指定速度で実行される
2. 低電圧時に停止する
3. 過大速度が1000へ制限される
4. NaNセンサー値が拒否される

この実行環境にはCargoとrustcが存在しないため、Rustコンパイルの実測検証は未実施である。

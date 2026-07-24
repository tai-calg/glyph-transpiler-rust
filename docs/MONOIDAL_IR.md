# Glyph Monoidal IR

## 目的

Glyphの表面文法を増やさず、既存の積型と資源能力を横方向の合成として機械可読にする。

標準の図artifactへの出力はGlyph 0.4機能を使用する入力で有効になる。旧Glyph入力のartifact集合は互換性のため変更しない。`build_monoidal_ir`自体は既存の積型だけでも利用できる。

生成物:

- `monoidal-ir.json` — `glyph.monoidal-ir` version 1
- `monoidal.mmd` — `Tensor`と`Parallel`のMermaid図
- `index.md` — Monoidal structure節

## 意味

### Tensor

`*Output(a:A,b:B)`は、型レベルでは `A ⊗ B` として記録する。積コンストラクタ
`Output(f(x),g(y))`は、値レベルのTensorとして記録する。

複数の資源能力を同時に受け取る関数もTensor境界として記録する。

```glyph
!submit(buffer:own Buffer[Ready],fence:own Fence[Pending]):Submission
```

これは `own Buffer[Ready] ⊗ own Fence[Pending]` を入力能力環境として持つことを表す。

### Parallel

積コンストラクタの各引数が純粋で、`?`による早期returnを含まない場合だけ、各引数を
`Parallel`レーンとして記録する。

```glyph
>process(x:Input):Output=Output(decode(x.raw),measure(x.voltage))
```

このParallelはデータ依存上、順序を要求しないという意味であり、スレッド生成、GPU同時実行、
非同期実行を保証しない。実行スケジュールはHostまたは後段コンパイラが決める。

## 保守的な判定

次はParallelへ分類しない。

- `!`または`~`境界へ到達するレーン
- 動的calleeを含むレーン
- `?`を含み、最初に返るエラーが評価順に依存し得るレーン
- 純粋性を証明できない呼出し

資源Tensorも所有能力の同時保持を表すだけであり、自動並列化の証拠にはしない。

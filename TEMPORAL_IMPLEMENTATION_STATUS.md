# Glyph 時相制約 実装状況

## 完了

### R0: 全履歴参照モニタ

- `?name(params)=formula`
- `□`、`◇`、`◇duration`
- `>>`、`U`、`W`
- `Satisfied / Violated / Pending`
- `step`、`verdict`、`finish`、`reset`
- 有限トレース参照評価器

### R1: 意味論固定

- 期限ちょうどを含む
- 時刻逆行を拒否し、同一時刻を許可
- 空トレースは`Pending`
- 空虚な含意を明示
- strong/weak untilの終端差を固定
- `□◇`、`◇□`の有限終端テスト
- 時相原子式から外部作用、失敗伝播、動的呼出しを禁止
- 純粋Glyph関数の直接・推移的検査

### R2: 頻出形の逐次モニタ

次の形について、全履歴を持たない`<Name>StreamingMonitor`を生成する。

```text
□P
◇P
◇d P
P U Q
P W Q
□(P >> Q)
□(P >> ◇Q)
□(P >> ◇d Q)
□◇P
□◇d P
◇□P
```

ここで瞬時状態式`P/Q`は、原子式と`!`、`&`、`|`、`>>`の組合せを含められる。

参照モニタと逐次モニタへ同一の決定的擬似ランダム観測列を入力し、各`step`と`finish`の判定一致をRustテストで検査する。

## 生成API

参照モニタ:

```rust
AckMonitor
```

逐次モニタ:

```rust
AckStreamingMonitor
```

両者は次の操作を共有する。

```rust
new()
step(at_ms, ...)
verdict()
finish()
reset()
```

逐次モニタは`Vec<Observation>`を持たず、式固有のbit、時刻、未解決期限だけを保持する。

## 未完了

- 任意の入れ子式に対する一般formula progression
- 参照／逐次生成モードの選択構文
- 違反時刻、発火時刻、期限を返す反例情報
- ID付き`send(id)`／`ack(id)`相関
- キー付き未解決義務と期限管理
- 長時間ベンチマークとメモリ測定
- ホスト周期実行、async統合例

未対応の一般式には参照モニタだけを生成し、誤った逐次最適化は行わない。

# Glyph temporal constraints

Glyphの`?`トップレベル宣言は、単一状態ではなく時刻付き状態列に対する制約を記述する。

```glyph
*O(send,ack,closed,auth,beat,stable:b)

?ack(*O)=□(send>>◇5s ack)
?safe(*O)=□(!auth>>closed)
?auth(*O)=closed U auth
?wait(*O)=closed W auth
?beat(*O)=□◇1s beat
?conv(*O)=◇□stable
```

## 記法

| 記法 | 意味 |
|---|---|
| `?name(params)=P` | 時相制約の宣言 |
| `□P` | すべての観測点で`P` |
| `◇P` | 現在または将来の観測点で`P` |
| `◇5s P` | 現在から5秒以内に`P` |
| `P>>Q` | `P`ならば`Q` |
| `P U Q` | `Q`が成立するまで`P`を維持し、最終的に`Q`が成立する |
| `P W Q` | `Q`が成立するまで`P`を維持する。`Q`は成立しなくてもよい |
| `!P`, `P&Q`, `P|Q` | 否定、論理積、論理和 |

`◇`の時間単位は整数の`ms`、`s`、`m`に限定する。`0.5s`ではなく`500ms`と書く。

## 優先順位

高い順に次の順序で解析する。

```text
! □ ◇
U W
&
|
>>
```

`>>`は右結合である。

```text
A>>B>>C = A>>(B>>C)
```

## 生成Rust

各制約は独立したモニタへ変換される。

```rust
let mut monitor = AckMonitor::new();

monitor.step(
    0,     // 単調増加するミリ秒時刻
    true,  // send
    false, // ack
    true,  // closed
    false, // auth
    false, // beat
    false, // stable
);

let verdict = monitor.step(4000, false, true, true, false, false, false);
```

判定は3値で返す。

```rust
pub enum TemporalVerdict {
    Satisfied,
    Violated,
    Pending,
}
```

`step`は実行途中の判定、`finish`は有限トレースを終了した後の判定に使う。

- `□P`は`P`が偽になった時点で`Violated`になる。
- `◇P`は`P`が成立するまで`Pending`であり、未成立のまま`finish`すると`Violated`になる。
- `P U Q`は`Q`未成立のまま`finish`すると`Violated`になる。
- `P W Q`は`P`を維持したまま`finish`すると`Satisfied`になる。
- `□◇P`と`◇□P`は無限実行に関する性質なので、通常は実行途中で最終的な成立を確定しない。

## 観測モデル

`step`の1回を1観測点とする。

- イベント値は、そのイベントが起きた観測点だけ`true`にする。
- 状態値は、その状態が継続する間`true`を渡す。
- `at_ms`は単調非減少でなければならない。
- モニタは時計を取得しない。時間取得、周期実行、非同期処理はホスト側の責任とする。

時刻だけが進んでも`step`が呼ばれなければ、期限超過は検出されない。期限監視が必要なシステムでは、イベント発生時に加えて監視周期ごとに`step`を呼ぶ。

## 第1版の制限

- `X`（次状態）は扱わない。
- 過去時相演算子と量化子は扱わない。
- 複数要求と応答のID対応付けは自動生成しない。
- 状態述語には既存Glyph式を使う。時相演算子を含む部分式と通常式の境界には括弧を使う。
- 実装は有限トレースを保持して再評価するため、長時間運転向けの定数メモリ監視器ではない。

第1版の目的は、設計制約からRustテストと実行時モニタを同時生成し、反例を実装段階で検出できる最小系を作ることにある。

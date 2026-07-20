# Glyph temporal constraints

Glyphのトップレベル`?`宣言は、単一状態ではなく時刻付き状態列に対する制約を記述する。

```glyph
*O(send,ack,closed,auth,beat,stable:B)

?ack(*O)=A(send>>E 5s ack)
?safe(*O)=A(!auth>>closed)
?auth(*O)=closed U auth
?wait(*O)=closed W auth
?beat(*O)=AE 1s beat
?conv(*O)=EA stable
```

## 記法

| 記法 | 意味 |
|---|---|
| `?name(params)=P` | 時相制約の宣言 |
| `A P` | すべての観測点でP |
| `E P` | 現在または将来の観測点でP |
| `E 5s P` | 現在から5秒以内にP |
| `P>>Q` | PならばQ |
| `P U Q` | Qが成立するまでPを維持し、最終的にQが成立する |
| `P W Q` | Qが成立するまでPを維持する。Qは成立しなくてもよい |
| `!P`, `P&Q`, `P|Q` | 否定、論理積、論理和 |

時間単位は整数の`ms`、`s`、`m`に限定する。`0.5s`ではなく`500ms`と書く。

Unicodeの`□`と`◇`は受理しない。AlwaysとEventuallyはASCIIの`A`と`E`で記述する。

## 演算子列

単項演算子は連結できる。

```glyph
AE 1s beat
EA stable
```

```text
AE 1s beat = A(E 1s beat)
EA stable  = E(A stable)
```

演算子列とオペランドの間には空白または`(`を置く。

```text
EA stable   # 演算子列
EA(stable)  # 演算子列
EAstable    # 一つの識別子
```

## 優先順位

高い順:

```text
! A E E duration
U W
&
|
>>
```

`>>`は右結合。

```text
P>>Q>>R = P>>(Q>>R)
```

## 生成Rust

各制約は独立した参照モニタへ変換される。

```rust
let mut monitor = AckMonitor::new();
monitor.step(0, true, false, true, false, false, false);
let verdict = monitor.step(4000, false, true, true, false, false, false);
```

判定は3値。

```rust
pub enum TemporalVerdict {
    Satisfied,
    Violated,
    Pending,
}
```

- `step`: 実行途中の判定
- `verdict`: 現在の判定
- `finish`: 有限トレース終了後の判定
- `reset`: モニタ初期化

有限トレース意味論:

- `A P`: Pが偽になった時点で`Violated`。反例なく終了すれば`Satisfied`
- `E P`: P成立まで`Pending`。未成立終了で`Violated`
- `E d P`: 期限内成立で`Satisfied`。期限超過または未解決終了で`Violated`
- `P U Q`: Q前のP違反、またはQ未成立終了で`Violated`
- `P W Q`: Q未成立でもPを維持したまま終了すれば`Satisfied`
- `AE P`と`EA P`: 通常は実行途中で最終成立を確定しない

## 逐次モニタ

頻出形には全履歴を保存しない`<Name>StreamingMonitor`も生成する。

```text
A P
E P
E d P
P U Q
P W Q
A(P >> Q)
A(P >> E Q)
A(P >> E d Q)
AE P
AE d P
EA P
```

安全な専用変換がない一般入れ子式には参照モニタだけを生成する。

## 観測モデル

`step`の1回を1観測点とする。

- イベント値は、そのイベントが起きた観測点だけ`true`
- 状態値は、その状態が継続する間`true`
- `at_ms`は単調非減少
- モニタは時計を取得しない
- 時間取得、周期実行、非同期処理はホスト側の責任

時刻だけが進んでも`step`が呼ばれなければ期限超過は検出されない。期限監視が必要なシステムでは、イベント時に加えて監視周期ごとに`step`を呼ぶ。

## 制限

- `X`は扱わない
- 過去時相演算子と量化子は扱わない
- 複数要求と応答のID対応付けは自動生成しない
- 状態述語は純粋かつ決定的でなければならない
- 時相演算子を含む部分式と通常式の境界には括弧を使う

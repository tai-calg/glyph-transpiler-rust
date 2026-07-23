# Glyph 時相制約設計書

## 1. 目的

Glyphは型、純粋関数、状態遷移、作用境界に加えて、**時刻付き状態列に対する制約**を記述する。

```text
型宣言       状態空間を定義する
純粋関数     状態または値の変換を定義する
machine      状態遷移の骨格を定義する
時相制約     許される実行履歴を定義する
```

通常の真偽式は一つの状態を評価する。時相式は次の観測列を評価する。

```text
(t0, s0) -> (t1, s1) -> (t2, s2) -> ...
```

対象:

- 常に成立すべき安全条件
- 最終的に成立すべき進行条件
- 要求と応答の対応
- 応答期限
- 条件成立まで維持すべき状態
- 最終的な安定化

## 2. 設計原則

1. 1制約を原則1行で記述する。
2. 時相演算子は通常の型名・変数名と視覚的に区別する。
3. 表面構文はASCIIだけで入力できる。
4. 通常式ASTと時相式ASTを分離する。
5. 時刻取得、周期実行、async、ドライバはRust hostへ残す。
6. 実行途中の未確定状態を成功・失敗へ誤分類しない。
7. 参照モニタと逐次モニタは同じ意味論を共有する。
8. source lineはrawマクロ展開後も元`.glyph`へ戻す。

## 3. 表面構文

### 制約宣言

```glyph
?name(params)=formula
```

例:

```glyph
*Observation(send,ack,closed,authorized,heartbeat,stable:B)

?ack(*Observation)=@A(send >> @E 500ms ack)
?safe(*Observation)=@A(!authorized >> closed)
?hold(*Observation)=closed U authorized
?weak_hold(*Observation)=closed W authorized
?live(*Observation)=@A@E 1s heartbeat
?converges(*Observation)=@E@A stable
```

`?`は構文位置で意味を分ける。

```text
expression?              Result失敗伝播
?name(params)=formula    時相制約宣言
```

### 時相演算子

| 記法 | 名称 | 意味 |
|---|---|---|
| `!P` | not | Pではない |
| `P&Q` | and | PかつQ |
| `P\|Q` | or | PまたはQ |
| `P>>Q` | implies | PならばQ |
| `@A P` | always | 現在以降の全観測点でP |
| `@E P` | eventually | 現在以降のどこかでP |
| `@E 500ms P` | bounded eventually | 500ms以内のどこかでP |
| `P U Q` | strong until | QまでPを維持し、Qは最終的に成立する |
| `P W Q` | weak until | QまでPを維持する。Qは成立しなくてもよい |

AlwaysとEventuallyには必ず`@`を付ける。

```glyph
@A P
@E P
@A@E 1s P
@E@A P
```

次は受理しない。

```glyph
A P       # 裸の演算子
E P
AE P
EA P
□P        # Unicode
◇P
@AE P     # 各演算子に@がない
```

`A`と`E`は時相演算子名として予約し、rawマクロまたはASTマクロ名に使えない。

```glyph
@A=other  # エラー
@E(x)=x   # エラー
```

### 演算子境界

演算子と識別子の間には空白または`(`を置く。

```text
@E@A stable     valid
@E@A(stable)    valid
@E@Astable      invalid
EAstable        通常識別子
```

### 時間リテラル

```text
500ms
5s
2m
```

規則:

- 整数のみ
- `ms`、`s`、`m`のみ
- 0は禁止
- 内部表現は`u64`ミリ秒
- `0.5s`ではなく`500ms`

## 4. 文法

```text
spec          := "?" Name "(" params? ")" "=" formula
formula       := implication
implication   := disjunction (">>" implication)?
disjunction   := conjunction ("|" conjunction)*
conjunction   := until_expr ("&" until_expr)*
until_expr    := unary (("U" | "W") unary)*
unary         := "!" unary
               | "@A" unary
               | "@E" duration? unary
               | "(" formula ")"
               | atom
duration      := Integer ("ms" | "s" | "m")
atom          := 既存Glyph真偽式
```

優先順位:

```text
1. ! @A @E @E duration
2. U W
3. &
4. |
5. >> 右結合
```

```text
P>>Q>>R = P>>(Q>>R)
```

## 5. 正規化

`@A`と`@E`は、rawプリプロセッサの後、compact syntax解析の前に時相式内部だけで正規化する。

```text
original Glyph
  ↓ reserved-name validation
raw preprocessor
  ↓
temporal sigil normalization
  @A -> internal Always token
  @E -> internal Eventually token
  ↓
compact syntax
  ↓
FormulaParser
```

時相sigil正規化はトップレベル`?`宣言だけを処理する。通常のGlyph式にある`@`構文へ影響しない。

行数は変えない。rawマクロ展開で変化した行番号は既存の`PreprocessResult`で元行へremapする。

## 6. AST

```text
Formula
├── Atom(Expr)
├── Not(Formula)
├── And(Formula, Formula)
├── Or(Formula, Formula)
├── Implies(Formula, Formula)
├── Always(Formula)
├── Eventually(Formula)
├── Within(milliseconds, Formula)
└── Until(hold, target, weak)
```

演算子列は専用ノードにしない。

```text
@A@E P = Always(Eventually(P))
@E@A P = Eventually(Always(P))
```

## 7. 観測モデル

```text
trace = [(t0, o0), (t1, o1), ..., (tn, on)]
t0 <= t1 <= ... <= tn
```

- `step`の1回を1観測点とする。
- 同時刻の複数観測を許可する。
- イベント値は発生点だけ`true`にする。
- 状態値は状態継続中`true`にする。
- モニタは時計を取得しない。
- hostが単調非減少の`at_ms`を渡す。

時刻だけが進んでも`step`が呼ばれなければ期限超過を検出できない。期限監視が必要なシステムはイベント時と監視周期ごとに`step`を呼ぶ。

## 8. 有限トレース意味論

判定は3値。

```rust
pub enum TemporalVerdict {
    Satisfied,
    Violated,
    Pending,
}
```

- `@A P`: Pが偽になれば`Violated`。反例なく終了すれば`Satisfied`
- `@E P`: P成立まで`Pending`。未成立終了で`Violated`
- `@E d P`: 期限内成立で`Satisfied`。期限超過で`Violated`
- `P U Q`: Q前のP違反、またはQ未成立終了で`Violated`
- `P W Q`: Q未成立でもP維持のまま終了すれば`Satisfied`
- `@A@E P`、`@E@A P`: 通常は実行途中で最終成立を確定しない

## 9. 生成Rust API

各制約から参照モニタを生成する。

```rust
let mut monitor = AckMonitor::new();
monitor.step(0, true, false);
let verdict = monitor.step(400, false, true);
```

共通操作:

```text
new       初期化
step      観測追加と途中判定
verdict   観測を追加せず途中判定
finish    有限トレース終了判定
reset     初期状態へ戻す
```

頻出形には全履歴を保存しない`<Name>StreamingMonitor`も生成する。

```text
@A P
@E P
@E d P
P U Q
P W Q
@A(P >> Q)
@A(P >> @E Q)
@A(P >> @E d Q)
@A@E P
@A@E d P
@E@A P
```

安全な専用変換がない一般式には参照モニタだけを生成する。

## 10. 検証規則

状態述語は純粋かつ決定的でなければならない。

拒否するもの:

- `!effect()`への直接・間接到達
- 未知の関数呼出し
- 動的な関数呼出し
- Result失敗伝播`?`
- 型がboolでない述語
- 0以下または`u64`範囲外の時間境界
- 重複制約名
- 生成monitor名との衝突

## 11. 不変条件

1. 表面構文として受理するAlways/Eventuallyは`@A` / `@E`だけである。
2. 裸の`A/E/AE/EA`を互換受理しない。
3. `A`と`E`をマクロ名として受理しない。
4. 時相sigil正規化は行数を変えない。
5. rawマクロ展開後の診断は元の呼出し行を指す。
6. 参照モニタと逐次モニタは同じ有限トレース意味論を持つ。
7. モニタは時計、thread、async runtime、I/Oを所有しない。

## 12. 非目標

- `X P`による次状態参照
- 過去時相演算子
- 一階量化子
- ID付き要求と応答の自動相関
- 分散時計の同期
- 連続時間信号の補間
- 完全なLTL/MTLモデル検査
- Rust所有権、async runtime、driverの再実装

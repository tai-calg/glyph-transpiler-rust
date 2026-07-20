# Glyph 時相制約設計書

## 1. 目的

Glyphに、型・変換・作用境界だけでなく、**時刻付き状態列に対する制約**を記述する能力を加える。

Glyph全体を次の3層として扱う。

```text
型宣言       状態空間を定義する
純粋関数     状態または値の変換を定義する
時相制約     許される実行列を定義する
```

通常の真偽式が「現在の一状態」を評価するのに対し、時相式は次のような観測列を評価する。

```text
(t0, s0) -> (t1, s1) -> (t2, s2) -> ...
```

これにより、以下を同じ`.glyph`ファイルからRustコードと検証器へ変換する。

- 常に成立すべき安全条件
- 最終的に成立すべき進行条件
- 要求と応答の対応
- 応答期限
- ある条件が成立するまで維持すべき条件
- 最終的な安定化

## 2. 設計目標

1. 1制約を原則1行で記述できること
2. 既存のGlyph記号を可能な限り再利用すること
3. 同じ入力から決定的に同じRustを生成すること
4. 通常式のASTと時相式のASTを分離すること
5. 時刻取得、周期実行、async、ドライバをホスト側へ残すこと
6. 実行途中の未確定状態を誤って成功または失敗にしないこと
7. 参照実装と最適化実装が同じ意味論を共有すること

## 3. 非目標

第1版では次を対象外とする。

- `X P`による次状態参照
- 過去時相演算子
- 一階量化子
- ID付き要求と応答の自動相関
- 分散時計の同期
- 連続時間信号の補間
- 不規則な観測間を暗黙に補完すること
- 完全なLTL/MTLモデル検査器
- Rustの型検査、所有権検査、asyncランタイムの再実装

`X`を除外する理由は、「次」が観測粒度に依存し、内部状態を1個追加しただけで仕様の真偽が変わるためである。同期回路向けに導入する場合は、将来`Xtick`のように遷移単位を明示した別機能として設計する。

## 4. 表面構文

### 4.1 制約宣言

```glyph
?name(params)=formula
```

例:

```glyph
*O(send,ack,closed,auth,beat,stable:b)

?ack(*O)=□(send>>◇5s ack)
?safe(*O)=□(!auth>>closed)
?auth(*O)=closed U auth
?wait(*O)=closed W auth
?beat(*O)=□◇1s beat
?conv(*O)=◇□stable
```

`?`は式末尾ではRustの失敗伝播、トップレベル行頭では時相制約宣言を表す。構文位置によって一意に区別する。

### 4.2 演算子

| 記法 | 名称 | 意味 |
|---|---|---|
| `!P` | 否定 | Pではない |
| `P&Q` | 論理積 | PかつQ |
| `P\|Q` | 論理和 | PまたはQ |
| `P>>Q` | 含意 | PならばQ |
| `□P` | always | 現在以降の全観測点でP |
| `◇P` | eventually | 現在以降のどこかでP |
| `◇5s P` | bounded eventually | 現在から5秒以内のどこかでP |
| `P U Q` | strong until | Qが成立するまでPを維持し、Qは最終的に成立する |
| `P W Q` | weak until | Qが成立するまでPを維持するが、Qは成立しなくてもよい |

`within 5s P`という単語形式は導入せず、`◇5s P`へ圧縮する。

### 4.3 優先順位

高い順に次とする。

```text
既存Glyphの原子式
! □ ◇
U W
&
|
>>
```

`>>`だけは右結合とする。

```text
A>>B>>C = A>>(B>>C)
```

複合式では意味を明示するため括弧を推奨する。

```glyph
?ack(*O)=□(send>>◇5s ack)
```

### 4.4 時間リテラル

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
- 秒と分はコンパイル時にミリ秒へ変換
- `0.5s`ではなく`500ms`と書く

## 5. 文法

```text
spec        := "?" Name "(" params? ")" "=" formula

formula     := implication
implication := disjunction (">>" implication)?
disjunction := conjunction ("|" conjunction)*
conjunction := until_expr ("&" until_expr)*
until_expr  := unary (("U" | "W") unary)*
unary       := "!" unary
             | "□" unary
             | "◇" duration? unary
             | "(" formula ")"
             | atom

duration    := Integer ("ms" | "s" | "m")
atom        := 既存Glyph真偽式
```

`atom`は既存の式パーサーへ渡す。これにより比較、論理式、関数呼出し、フィールド参照、単語マクロを再利用する。

## 6. 状態モデル

### 6.1 観測列

各制約モニタは次の有限列を保持または逐次処理する。

```text
trace = [(t0, o0), (t1, o1), ..., (tn, on)]
```

条件:

```text
t0 <= t1 <= ... <= tn
```

同時刻の複数観測は許可する。順序は`step`呼出し順で決まる。

### 6.2 イベントと状態

Glyphはフィールドがイベントか状態かを自動判定しない。呼出し側が意味を決める。

イベント例:

```text
send = 発生した観測点だけtrue
ack  = 発生した観測点だけtrue
```

状態例:

```text
closed = 閉状態が続く間true
stable = 安定状態が続く間true
```

イベントを一度trueにした後もtrueのまま保持すると、時相式の意味が変わる。設計書またはアダプター層で各観測値を`event`か`state`として明示する必要がある。

### 6.3 時刻源

モニタは時計を取得しない。ホストが単調増加する`at_ms: u64`を渡す。

```rust
monitor.step(at_ms, ...);
```

推奨時刻源は単調時計であり、壁時計の時刻修正を直接渡さない。

## 7. AST

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

`□◇P`と`◇□P`は専用ノードにしない。

```text
□◇P = Always(Eventually(P))
◇□P = Eventually(Always(P))
```

構文糖を増やさず、入れ子可能な小さい核で表現する。

## 8. コンパイルパイプライン

```text
.glyph source
    |
    +-- extract_specs
    |      +-- ?name(params)=formula を抽出
    |      +-- FormulaParser
    |      +-- Formula AST
    |      `-- 元行を空行へ置換して行番号を維持
    |
    +-- compact syntax expansion
    |
    +-- core Glyph parser
    |      `-- 型、関数、作用境界のProgram AST
    |
    +-- RustGenerator
    |      `-- 通常Rust
    |
    `-- TemporalRustGenerator
           `-- 制約モニタRust
```

時相式を通常の`ExprParser`へ混在させない。通常式は1状態、時相式は状態列を対象とし、型も評価方法も異なるためである。

## 9. 生成Rust API

制約:

```glyph
?ack(*O)=□(send>>◇5s ack)
```

生成APIの概形:

```rust
pub enum TemporalVerdict {
    Satisfied,
    Violated,
    Pending,
}

pub struct AckMonitor {
    // 参照実装では観測列を保持
}

impl AckMonitor {
    pub fn new() -> Self;

    pub fn step(
        &mut self,
        at_ms: u64,
        send: bool,
        ack: bool,
        closed: bool,
        auth: bool,
        beat: bool,
        stable: bool,
    ) -> TemporalVerdict;

    pub fn verdict(&self) -> TemporalVerdict;
    pub fn finish(&self) -> TemporalVerdict;
    pub fn reset(&mut self);
}
```

### 9.1 `step`

観測を1件追加し、まだ実行が続く前提で評価する。

```text
closed = false
```

### 9.2 `verdict`

現在保存されている観測列を、実行がまだ続く前提で再評価する。観測は追加しない。

### 9.3 `finish`

現在の観測列で実行が終了したとして評価する。

```text
closed = true
```

`◇P`やstrong untilは、`finish`時点まで目標が成立していなければ違反になる。

### 9.4 `reset`

保存済み観測と判定状態を初期化する。

## 10. 3値意味論

有限トレースの実行途中では、通常のboolだけでは不足する。

```text
Satisfied  現在の情報だけで成立が確定
Violated   現在の情報だけで違反が確定
Pending    将来の観測によって成立または違反が変わり得る
```

### 10.1 原子命題

観測点`i`で既存Glyph式を評価する。

```text
true  -> Satisfied
false -> Violated
```

### 10.2 否定

```text
!Satisfied = Violated
!Violated  = Satisfied
!Pending   = Pending
```

### 10.3 論理積

```text
どちらかがViolated          -> Violated
両方がSatisfied             -> Satisfied
それ以外                    -> Pending
```

### 10.4 論理和

```text
どちらかがSatisfied         -> Satisfied
両方がViolated              -> Violated
それ以外                    -> Pending
```

### 10.5 含意

```text
P>>Q = !P | Q
```

前件`P`が成立しなければ式は成立する。これは空虚な真である。

```glyph
□(send>>◇5s ack)
```

では、`send`が一度も起きなければ違反にならない。送信自体も必要なら別制約を置く。

```glyph
?send_occurs(*O)=◇send
```

## 11. 時相演算子の意味論

以下の評価開始位置を`i`とする。

### 11.1 Always

```text
□P
```

- `i`以降のどこかでPが違反: `Violated`
- 実行途中で違反未検出: `Pending`
- `finish`時に全観測点で成立: `Satisfied`

実行途中に`Satisfied`を返さない。将来Pが破られる可能性が残るためである。

### 11.2 Eventually

```text
◇P
```

- `i`以降でPが成立: `Satisfied`
- 実行途中で未成立: `Pending`
- `finish`時まで未成立: `Violated`

### 11.3 Bounded Eventually

```text
◇d P
```

開始時刻を`trace[i].at_ms`とし、期限を次で定義する。

```text
deadline = trace[i].at_ms + d
```

期限ちょうどを含む。

```text
trace[j].at_ms <= deadline
```

- 期限内にP成立: `Satisfied`
- 最新観測時刻が期限を超過: `Violated`
- `finish`時までにP未成立: `Violated`
- それ以外: `Pending`

加算は`saturating_add`を使い、`u64`オーバーフローを最大値へ飽和させる。

### 11.4 Strong Until

```text
P U Q
```

- いつかQが成立する
- Qが最初に成立する前の全観測点でPが成立する
- Q成立後には要求しない

判定:

```text
Qより前にP違反       -> Violated
Q成立かつそれ以前P成立 -> Satisfied
実行途中でQ未成立     -> Pending
finish時にQ未成立     -> Violated
```

`P U Q`は不変条件の永久的切替を直接表さない。Q成立後の維持条件が必要なら右辺へ`□`を付ける。

```glyph
?mode(*O)=closed U □stable
```

### 11.5 Weak Until

```text
P W Q
```

次と同値である。

```text
(P U Q) | □P
```

判定:

```text
Qより前にP違反       -> Violated
Q成立かつそれ以前P成立 -> Satisfied
実行途中でQ未成立     -> Pending
finish時にQ未成立かつP継続 -> Satisfied
```

安全条件として「認可されるまでは閉じる。認可が永久に来なくても閉じ続ければよい」を表す場合に使う。

```glyph
?safe_wait(*O)=closed W auth
```

## 12. `□◇P`と`◇□P`

### 12.1 `□◇P`

無限トレースでは、どの時点から見ても将来Pがあり、Pが繰り返し起こることを表す。

有限トレースの実行途中では最終成立を確定できない。現在の参照実装では、`finish`を有限トレース終端として評価するため、最後の各評価位置からPへ到達できるかを検査する。

本来の無限系列上の意味と有限系列上の終端意味は同一ではない。API利用者は、無限実行の活性保証を`finish()`だけで証明したと解釈してはならない。

実行可能な監視へ落とす場合は有界化する。

```glyph
?heartbeat(*O)=□◇1s beat
```

### 12.2 `◇□P`

無限トレースでは、ある時点以降ずっとPが成立することを表す。

有限トレースでは、終端直前だけPが成立していても候補になり得る。このため、実運用で安定化を要求するなら、最低継続時間や別の状態機械を加えるべきである。

例:

```text
stable_since_msを状態として持つ
□(stable >> now-stable_since >= 5s)
```

または将来、`□5s P`のような有界alwaysを追加する。

## 13. 現在の参照実装

### 13.1 方式

各モニタが全観測を`Vec<Observation>`へ保存し、`step`、`verdict`、`finish`のたびに式木を再評価する。

```text
monitor
  trace: Vec<Observation>
  eval_0(i, closed)
  eval_1(i, closed)
  ...
```

### 13.2 利点

- 意味論と生成コードの対応が見やすい
- 反例となる観測列を保持できる
- ネストした式を一様に評価できる
- 最適化前の基準実装として使える
- 省メモリ実装との等価性テストに使える

### 13.3 制約

観測数を`n`とすると、保存メモリは少なくとも`O(n)`になる。

評価時間は式の形に依存する。`□`、`◇`、`U/W`が入れ子になると、同じ接尾列を繰り返し走査するため、単純な`O(n)`を超える場合がある。

したがって現在の実装は次の用途に限定する。

- 設計検証
- 小規模テスト
- 意味論確認
- 生成コードのデモ

長時間稼働する組み込み・サーバー監視へそのまま投入しない。

## 14. 意味論監査

最適化前に、次の項目をテストと文書で固定する。

### S0. 観測と時刻

- 同一時刻の複数観測順序
- 時刻逆行時の挙動
- 観測のない時間帯をどう扱うか
- 期限ちょうどを含むこと
- 最終観測が期限ちょうどの場合
- `saturating_add`時の最大期限

### S1. 有限トレース終端

- 空トレースの`finish`
- `□P`の有限終端
- `◇P`の有限終端
- `U/W`の終端差
- ネストした`□◇`、`◇□`の終端意味
- `Pending`を含む部分式の伝播

### S2. 空虚な真

- `P>>Q`でPが一度も成立しない場合
- `□(request>>◇response)`でrequestがない場合
- 必要に応じて非空性制約を別に要求する設計

### S3. Stuttering

`X`を含まない式について、観測値が同一の状態を途中へ追加しても真偽が変化しないことを確認する。ただし時間付き`◇d`では、追加観測そのものではなく時刻の進行が結果へ影響する。

### S4. Until境界

- Qが初期位置で成立する場合、Pを要求しないこと
- PとQが同一観測点で成立する場合
- Q成立前にPが一度偽になる場合
- Q成立後にはPを要求しないこと
- `P U □Q`の期待動作

### S5. 原子式

- 時相制約引数以外の名前解決
- 外部作用呼出しの禁止または制限
- `?`失敗伝播を原子式内で許可するか
- 原子式が純粋かつ決定的であること

## 15. 省メモリ化設計

### 15.1 基本方針

参照実装を残し、別の逐次モニタ生成器を追加する。

```text
Formula AST
   +-- ReferenceTraceGenerator
   |      `-- 全トレース保存・再評価
   |
   `-- StreamingMonitorGenerator
          `-- 残余式または専用状態機械
```

両者へ同じ観測列を入力し、各時点のverdictと`finish`結果が一致することを差分テストする。

### 15.2 演算子別の最小状態

単純形では次の状態へ縮約できる。

| 式 | 保持状態 |
|---|---|
| `□P` | 違反済みbit |
| `◇P` | 成立済みbit |
| `◇d P` | 開始時刻、成立済みbit |
| `P U Q` | P違反済み、Q到達済み |
| `P W Q` | P違反済み、Q到達済み |

ただし一般の入れ子式をすべて単純なbitへ変換できるとは限らない。

### 15.3 Formula progression

各観測ごとに、元の式を「残りの未来で満たすべき式」へ進める。

```text
progress(formula, observation, delta_t) -> residual_formula
```

例:

```text
progress(□P, s)
  P(s)=false -> false
  P(s)=true  -> □P

progress(◇P, s)
  P(s)=true  -> true
  P(s)=false -> ◇P
```

時間付き式は残り時間も状態へ持つ。

```text
◇5000ms P
  --1000ms経過--> ◇4000ms P
```

同値な残余式を正規化・共有し、式木の無制限な増大を防ぐ。

### 15.4 応答義務

```glyph
□(send>>◇5s ack)
```

は、`send`ごとに期限付き義務を発生させると解釈できる。

```text
send at t -> ack must occur by t+5000
```

IDなしで同じ`ack`が全未解決sendを満たせる意味論なら、最古の未解決期限だけで違反検出できる場合がある。

一方、次のようなID対応を導入すると、キーごとの義務が必要になる。

```glyph
send(id) -> ack(id)
```

この場合のメモリは`O(未解決ID数)`であり、一般には定数メモリにできない。省メモリ化の目標は「常にO(1)」ではなく、**全履歴O(n)を、意味上必要な未解決義務O(k)へ縮約すること**とする。

### 15.5 期限管理

多数の期限付き義務を扱う場合は、次の候補を比較する。

- 最古期限のみ保持
- キー別HashMap
- 期限順min-heap
- 時間幅が固定ならリングバッファまたはタイミングホイール

第1版のIDなし命題論理では、式ごとの専用状態機械を優先する。

### 15.6 反例保持

全履歴を捨てると反例説明が弱くなる。次の2モードを用意する。

```text
release monitor  最小状態だけ保持
trace monitor    直近N件または全履歴を保持
```

違反時には次を出せるようにする。

- 制約名
- 違反確定時刻
- 発火元観測時刻
- 期限
- 直近の関連観測

## 16. 最適化後のランタイム境界

生成モニタは以下を行わない。

- スレッド生成
- sleep
- 時計取得
- ロック方針の決定
- async executor選択
- ログ出力先の決定
- 違反時の停止、再試行、フェイルセーフ操作

ホスト側が次を担当する。

```text
observe system
    -> acquire monotonic time
    -> monitor.step(...)
    -> handle verdict
```

違反時の作用は`!`境界として別に定義できる。

## 17. テスト戦略

### 17.1 パーサーテスト

- 全演算子
- 優先順位
- 右結合含意
- 積型引数展開
- 時間単位変換
- 不正時間
- 重複制約名
- 未定義積型
- 括弧不整合

### 17.2 意味論テスト

各演算子について、次を分ける。

```text
step中の判定
finish後の判定
```

最低ケース:

- alwaysの途中違反
- eventuallyの途中成立
- eventuallyの終端違反
- withinの期限内成立
- withinの期限ちょうど成立
- withinの期限超過
- strong untilの目標未到達
- weak untilの目標未到達
- untilの維持条件違反
- 空虚な含意
- ネスト式

### 17.3 差分テスト

ランダムな有限観測列を生成し、次を比較する。

```text
reference trace monitor
streaming monitor
```

各`step`後と`finish`後の判定が完全一致しなければならない。

### 17.4 Rust検証

CIで次を実行する。

```text
Python unit tests
決定的Rust再生成
cargo fmt
cargo test
cargo run
cargo clippy
```

## 18. 実装段階

### R0: 参照実装

完了条件:

- `?`制約宣言
- `□`、`◇`、`◇duration`
- `>>`、`U`、`W`
- Formula AST
- 3値判定
- Rustモニタ生成
- Python/Rustテスト

現在この段階まで完了している。

### R1: 意味論固定

- 第14章の監査ケースをすべてテスト化
- `□◇`、`◇□`の有限終端意味を明記
- 原子式の純粋性制約を確定
- イベントと状態の観測規約を文書化
- 反例表現を定義

### R2: 逐次モニタ

- formula progressionまたは専用状態機械
- 全履歴保存を廃止可能にする
- 参照実装との差分テスト
- 時間・メモリ計測
- リリースモードとトレースモード

### R3: 相関付き義務

- `send(id)`と`ack(id)`の対応
- キー付きモニタ
- 未解決義務数の上限
- 期限管理方式
- 重複IDと再送の意味論

### R4: 統合

- ホストアダプター例
- 組み込み周期実行例
- asyncサービス例
- 違反時の`!`作用境界
- 生成テストとランタイムモニタの共通利用

## 19. 受入条件

時相制約機能は、次を満たしたとき本番利用可能とする。

1. 文法と意味論が本書に一致する
2. 参照実装と逐次実装の差分テストが通る
3. 時刻境界テストが全て通る
4. 長時間実行でメモリが全履歴長へ比例しない
5. 違反時に制約名と原因時刻を取得できる
6. 同じGlyphから決定的に同じRustが生成される
7. `cargo test`とClippyが通る
8. ホスト側が時計・実行方式・作用処理を交換できる

## 20. 設計上の結論

Glyphの時相制約は、処理を実装する機能ではない。**許される実行列と禁止される実行列を宣言し、その宣言から実行可能なRustモニタを生成する機能**である。

```text
型          何が存在できるか
関数        どう変換できるか
時相制約    どの実行履歴が許されるか
```

現在の全履歴参照実装は完成形ではなく、意味論を目で追え、最適化実装の正しさを比較できる基準器である。次工程では意味論を先に固定し、その後に全履歴`O(n)`を未解決義務`O(k)`または式固有の定数状態へ縮約する。

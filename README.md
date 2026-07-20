# Glyph Rust

頻出するシステム設計概念を短い記号で記述し、通常のRustコードと実行時モニタを生成する依存ゼロの小型トランスパイラ。

## 最上位目的

> 型、純粋計算、状態遷移、作用境界、実行履歴制約を、構文位置から一意に読める形で記述する。

| 記号 | 意味 | Rustへの展開 |
|---|---|---|
| `@` | 式中の単語マクロ | 識別子トークンを式へ展開 |
| `*` | 積型 | `struct` |
| `+` | 直和型 | `enum` |
| `>` | 純粋な変換 | `fn` |
| `!` | 外部作用との境界 | `crate::host::<name>` |
| 型位置の `T|E` | 成功型または失敗型 | `Result<T,E>` |
| ガード行の `>>` | 条件と結果の区切り | `if` / `else` |
| トップレベルの `?` | 時相制約 | Rustモニタ |
| 式末尾の `?` | 失敗の早期返却 | Rustの`?` |
| 式位置の `|` / `&` | 論理和 / 論理積 | `||` / `&&` |
| 式位置の `==` | 等値比較 | `==` |

`=`は宣言・定義の区切りだけに使う。式中の等値比較は必ず`==`と書く。

## 最短実行

必要環境:

- Python 3.10以上
- 生成Rustをビルドする場合のみCargo

```bash
python3 run.py
```

変換だけを実行:

```bash
python3 glyphc.py examples/controller.glyph \
  -o demo/src/generated.rs \
  --host-output demo/src/host.generated.rs
```

構文検査だけを実行:

```bash
python3 glyphc.py examples/controller.glyph --check
```

テスト:

```bash
python3 -m unittest discover -s tests -v
cargo test --manifest-path demo/Cargo.toml
cargo test --manifest-path demo-system/Cargo.toml
```

## 基本例

```glyph
@LOW=10.0
@HOT=80.0
@MAX=1000
@BAD=!finite(v)|!finite(t)|v<0.0
@BLOCK=s.v<LOW|s.t>HOT|s.r==0
@PIPE=exec(cmd(decode(v,t,r)?))

*S(v,t:F,r:U)
+C=Stop|Run(U)
+Error=BadSensor|Actuator
*Receipt(c:C)
*Observation(send,ack,closed,auth,beat,stable:B)

>decode(*S):S|Error
  BAD>>Err(BadSensor)
  _>>Ok(S(v,t,r))

>cmd(s:S):C
  BLOCK>>Stop
  _>>Run(min(s.r,MAX))

!exec(c:C):Receipt|Error=Ok(Receipt(c))
>run(*S):Receipt|Error=PIPE

?ack(*Observation)=A(send>>E 5s ack)
?safe(*Observation)=A(!auth>>closed)
?wait(*Observation)=closed W auth
?live(*Observation)=AE 1s beat
?conv(*Observation)=EA stable
```

## 型

### 長形式

```text
u8 u16 u32 u64
i8 i16 i32 i64
f32 f64 bool String
R<T,E>  -> Result<T,E>
O<T>    -> Option<T>
V<T>    -> Vec<T>
S       -> String
```

### 短縮型

短縮型は型位置だけで有効。

```text
F -> f32
D -> f64
U -> u16
I -> i32
B -> bool
T|E -> Result<T,E>
```

小文字の旧短縮型`f/d/u/i/b`は受理しない。値識別子との視覚的な混同を避けるため、短縮型を大文字へ統一している。

同じ型を持つフィールドはまとめて記述できる。

```glyph
*Point(x,y:F)
```

生成:

```rust
pub struct Point {
    pub x: f32,
    pub y: f32,
}
```

ユーザー定義型が`F`、`U`などと同名の場合は、ユーザー定義型を優先する。

## ガードとvariant pattern

通常の比較:

```glyph
>same(x,y:U):B
  x==y>>true
  _>>false
```

直和型の分解:

```glyph
+Command=Stop|Run(U)

>speed(command:Command):U
  command==Run(value)>>value
  command==Stop>>0
  _>>0
```

`command==Run(value)`は、`command`が`Run`であることを検査し、payloadを`value`へ束縛する。

```glyph
command==Run(system.sequence)
```

右辺が既存引数またはフィールド式の場合は束縛ではなく値比較になる。

## 時相論理

### 制約宣言

```text
?ConstraintName(parameters)=formula
```

例:

```glyph
?ack(send,ack:B)=A(send>>E 500ms ack)
```

意味は「すべての観測時点で、`send`が成立した場合は500ミリ秒以内に`ack`が成立する」。

### 表面構文

| Glyph | 数理表記 | 意味 |
|---|---|---|
| `!P` | `¬P` | 否定 |
| `P & Q` | `P ∧ Q` | 論理積 |
| `P | Q` | `P ∨ Q` | 論理和 |
| `P >> Q` | `P → Q` | 含意 |
| `A P` | `□P` | 常にP |
| `E P` | `◇P` | いつかP |
| `E 500ms P` | `◇≤500ms P` | 500ミリ秒以内にP |
| `P U Q` | `P U Q` | strong until |
| `P W Q` | `P W Q` | weak until |

`A`と`E`は時相式内の予約演算子。Unicodeの`□`と`◇`は受理しない。

### 演算子列と空白

単項演算子は連結できる。

```glyph
AE 1s beat
EA stable
```

それぞれ次を意味する。

```text
AE 1s beat = A(E 1s beat) = □◇≤1s beat
EA stable  = E(A stable)   = ◇□stable
```

演算子列とオペランドの間には空白または`(`を置く。

```text
EA stable   # E(A(stable))
EA(stable)  # E(A(stable))
EAstable    # EAstableという一つの識別子
```

この規則により、識別子を文字単位で推測して分割しない。

### 優先順位

高い順:

```text
1. 単項: ! A E E duration
2. Until: U W
3. 論理積: &
4. 論理和: |
5. 含意: >>  （右結合）
```

したがって、

```glyph
A send>>E ack
```

は次として解釈される。

```text
(A send) >> (E ack)
```

全体を常時制約にする場合は括弧を書く。

```glyph
A(send>>E ack)
```

### 有限トレース意味論

モニタは無限実行ではなく、開始から現在までの有限な観測列を評価する。

`TemporalVerdict`は次の3値。

```rust
pub enum TemporalVerdict {
    Satisfied,
    Violated,
    Pending,
}
```

- `Satisfied`: 現在の情報だけで成立が確定した
- `Violated`: 現在の情報だけで違反が確定した
- `Pending`: 将来の観測または`finish()`が必要

主要演算子の終了時意味論:

| 式 | 実行途中 | `finish()`時 |
|---|---|---|
| `A P` | 反例が出れば`Violated`。それ以外は`Pending` | 全観測点でPなら`Satisfied` |
| `E P` | Pが出れば`Satisfied` | Pが一度もなければ`Violated` |
| `E d P` | 期限内にPなら`Satisfied`。期限超過で`Violated` | 未解決なら`Violated` |
| `P U Q` | Q前にPが偽なら`Violated` | Q未到達なら`Violated` |
| `P W Q` | Q前にPが偽なら`Violated` | Q未到達でもP維持なら`Satisfied` |

`A(send>>E 5s ack)`では、`send`が一度も発生しなければ空虚に真となる。送信発生自体も要求する場合は別制約を追加する。

```glyph
?send_occurs(send:B)=E send
```

### 時刻

```rust
monitor.step(at_ms, ...);
```

`at_ms`はホストが渡す単調時刻。

- 同一時刻は許可
- 時刻逆行はpanic
- 期限ちょうどは期限内
- 時間単位は`ms`、`s`、`m`

### 生成モニタ

各制約について全履歴参照モニタを生成する。

```rust
<Name>Monitor
```

頻出形には全履歴を保存しない逐次モニタも生成する。

```rust
<Name>StreamingMonitor
```

逐次化対応形:

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

一般の入れ子式で安全な専用変換が定義されていない場合、参照モニタだけを生成する。

API:

```rust
monitor.step(at_ms, ...);
monitor.verdict();
monitor.finish();
monitor.reset();
```

時相原子式は純粋かつ決定的でなければならない。外部作用、失敗伝播、動的callee、未解決関数を含む原子式は拒否する。

## 外部作用

`!name(args):Ret`は外部作用境界を宣言する。

```glyph
!send(x:u8):u8|Error
```

呼出しは次へ展開される。

```rust
crate::host::send(x)
```

`=expression`を付けると試作実装を`host.generated.rs`へ生成する。

```glyph
!send(x:u8):u8|Error=Ok(x)
```

実機接続では`host.rs`をGPIO、UART、CANなどのアダプターへ差し替える。

## ディレクトリ

```text
glyph-rust/
├── glyphc.py
├── glyph/compiler.py
├── glyph/syntax.py
├── glyph/temporal.py
├── glyph/temporal_codegen.py
├── glyph/temporal_stream_codegen.py
├── glyph/artifacts.py
├── examples/controller.glyph
├── examples/system_controller.glyph
├── demo/
├── demo-system/
├── tests/
├── LANGUAGE.md
├── TEMPORAL_DESIGN.md
└── run.py
```

## 現在の制限

- 文字列リテラル、配列、ループ、参照、ライフタイム、ジェネリック関数は未対応
- 単語マクロは式専用で、引数を取らない
- 型検査はRustコンパイラへ委譲する
- 実機の外部作用は`crate::host`に実装する
- `X`、過去時相演算子、一階量化、ID付き要求応答相関は未対応
- 生成先はRust 2021 Editionを想定する

## ライセンス

MIT License

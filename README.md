# Glyph Rust

Glyphは、ソフトウェアの**構造・判断・状態・作用・時間制約・アルゴリズム骨格**を短いコードで記述し、同じ設計からStudio、Mermaid、型付き設計JSON、Rustを生成するDSLです。

Rustの代替として詳細実装をすべて書く言語ではありません。Glyphには人間とAIが確認すべき設計を残し、計算量やデータ構造まで作り込む処理は`~`でRustへ委譲します。

```text
自然言語・要求
      ↓
Glyphの設計モデル
├── Architecture
├── Data / Decision
├── State / Time
├── Algorithm skeleton
└── Effect / Rust boundary
      ↓
Rust実装・図・型付き設計JSON
```

## 起動

通常利用で覚えるコマンドは1つです。

```bash
python3 glyph.py examples/function_block.glyph
```

Glyph Studioの1プロセス内で、次を扱います。

- Glyphソースの編集と保存
- 自動再コンパイルと診断
- Architecture / State / Logic / Time
- 生成Rustとhost adapter
- `manual.rs`
- Typed AST / SymbolId / `:=` block metadata
- 生成物一覧

## 10分で書くアルゴリズム骨格

```glyph
system Planner
  input -> process
  process -> optimize
  optimize -> output

@MAX=100
+Command=Stop|Run(U)|Fault
+Error=Bad

>validate(x:U):U|Error=Ok(x)
~optimize(x:U):U # TODO: 計算量とデータ構造をRustで設計

>process(c:Command):U|Error
  speed :=
    c==Stop >> 0
    c==Run(n) >> n
    _ >> 0

  checked := validate(speed)?

  normalized :=
    checked
    /> |n| min(n,MAX)

  result := optimize(normalized)
  Ok(result)

!output(x:U):B
```

この1ファイルから、次を得ます。

```text
Architecture  input → process → optimize → output
Logic         match → validate → normalize → optimize
Rust          型、純粋関数、let、Result伝播
Manual        optimizeの型安全なRust雛形
Design JSON   中間値、ラムダ、SymbolId、source line
```

---

## `system`: 外側の構造

1接続を1行で書きます。

```glyph
system Door
  sensor -> ctl
  panel -> ctl
  ctl -> lock
  ctl -> log
```

component名は同名宣言へ自動bindingされます。

| 宣言 | Architecture上の種類 |
|---|---|
| `>name` | Glyph function |
| `~name` | Rust implementation |
| `!name` | effect boundary |
| 型名 | data |
| 未定義名 | external component |

---

## データ型

積型は`*`、直和型は`+`です。

```glyph
*Input(value:U,valid:B)
+Command=Stop|Run(U)|Fault(Error)
```

型位置では短縮型を使えます。

```text
F      f32
D      f64
U      u16
I      i32
B      bool
T|E    Result<T,E>
```

---

## 2種類の関数本体

### 1. 最終結果を直接選ぶガード関数

```glyph
+Kind=Negative|Zero|Positive

>classify(x:I):Kind
  x<0 >> Negative
  x==0 >> Zero
  _ >> Positive
```

上から最初に成立した節を返します。最後の`_`は必須の`else`です。

生成Rust:

```rust
pub fn classify(x: i32) -> Kind {
    if x < 0 {
        Kind::Negative
    } else if x == 0 {
        Kind::Zero
    } else {
        Kind::Positive
    }
}
```

この形式では各分岐が関数の最終結果です。分岐後に別の処理を続ける場合は、次の`:=`ブロックを使います。

### 2. 中間値を持つアルゴリズムブロック

```glyph
>normalize(x:I):I
  positive :=
    x<0 >> -x
    _ >> x

  limited :=
    positive>100 >> 100
    _ >> positive

  result :=
    limited>50 >> limited/2
    _ >> limited

  result
```

関数ブロックは、0個以上の中間値定義と、最後の返却式から構成されます。

```text
name := expression

name :=
  condition >> expression
  _ >> expression

final-expression
```

生成Rustでは通常の`let`になります。

```rust
pub fn normalize(x: i32) -> i32 {
    let positive = if x < 0 { -x } else { x };
    let limited = if positive > 100 { 100 } else { positive };
    let result = if limited > 50 { limited / 2 } else { limited };
    result
}
```

### `:=`は代入ではない

`:=`は変更可能な変数への代入ではなく、**一度だけ行う不変値の定義**です。

```glyph
value := first(input)
value := second(input) # エラー: 同名再定義
```

関数引数と同名の中間値も定義できません。各右辺は、それ以前に定義された値だけを参照できます。

### 単一式

```glyph
checked := validate(input)?
result := transform(checked)
```

### 条件分岐

```glyph
mode :=
  input.stop >> Stop
  input.fast >> Fast
  _ >> Normal
```

### variant pattern / match

```glyph
+Command=Stop|Run(U)|Fault(Error)

>speed(c:Command):U
  value :=
    c==Stop >> 0
    c==Run(n) >> n
    c==Fault(_) >> 0
    _ >> 0

  value
```

boolean条件とvariant patternを別の予約語に分けません。条件の形からRustの`if`またはpattern matchingへ生成します。

### `?`による失敗伝播

```glyph
>checked(x:U):U|Error
  value := validate(x)?
  Ok(value)
```

`?`は中間値の右辺でも使えます。生成Rustは`let value = validate(x)?;`になります。

---

## `/>`: 左から右への処理連結

```glyph
value /> f /> g
```

は次と同じ意味です。

```glyph
g(f(value))
```

視覚的に複数行へ分けられます。

```glyph
normalized :=
  value
  /> validate?
  /> convert
  /> encode
```

失敗を伝播する段には`?`を付けます。

```glyph
value /> validate? /> decide
```

---

## ラムダ

一度しか使わない短い局所変換は、名前付き関数を追加せずラムダで書けます。

```glyph
normalized :=
  value
  /> |x| x+1
  /> |x| min(x,MAX)
```

型を推論できない場合は明示します。

```glyph
value /> |x:U| x+1
```

現在のpipeline lambdaは次に限定しています。

- 1引数
- 単一式
- non-capturing
- pure
- `/>`の段として使用

外側の実行時変数をcaptureするラムダや、effectへ到達するラムダは拒否します。

### ラムダと`:=`の使い分け

| 状況 | 使用するもの |
|---|---|
| 値を一度だけ次段へ渡す | `/>`とラムダ |
| 一度しか使わない短い変換 | ラムダ |
| 分岐が合流した結果 | `:=` |
| 後続から複数回参照する値 | `:=` |
| 名前自体が設計上の意味を持つ節目 | `:=` |

冗長な書き方:

```glyph
a := x+1
b := min(a,MAX)
c := normalize(b)
c
```

推奨:

```glyph
x
/> |n| n+1
/> |n| min(n,MAX)
/> normalize
```

一方、分岐結果や再利用する値は`:=`で明示します。

---

## 再帰

名前付き純粋関数は直接再帰と相互再帰を記述できます。

```glyph
>sum(n:U):U
  n==0 >> 0
  _ >> n+sum(n-1)
```

単純な`parameter - constant`型自己再帰はTyped ASTで`structural`、その他の循環は`unchecked`として記録します。これは停止性の完全証明ではありません。

---

## `~`: 複雑なアルゴリズムをRustへ残す

計算量設計、複雑なデータ構造、SIMD、GPU、unsafe、外部crate固有処理などは、型契約とcall graph上の位置だけをGlyphに残します。

```glyph
*Graph(nodes:U,edges:U)
*Path(cost:U)

~shortest_path(graph:Graph,start:U,goal:U):Path
  # TODO: Dijkstra/A*、O(E log V)、メモリ配置をRustで設計

>plan(graph:Graph,start:U,goal:U):Path
  path := shortest_path(graph,start,goal)
  path
```

役割は次の通りです。

| 記号 | 意味 | 実装場所 |
|---|---|---|
| `>` | Glyphで記述するロジック | Glyph |
| `~` | 複雑な純粋アルゴリズム | `manual.rs` |
| `!` | 通信、ファイル、GPIO等の外部作用 | host adapter |

生成ロジックは`crate::manual::shortest_path(...)`を呼びます。Studioは初回だけ`.glyph/<source-stem>/manual.rs`へ、`todo!()`付きの型安全な雛形を作ります。

`manual.rs`は利用者所有です。保存・再コンパイル時に上書きしません。

`~`は純粋関数として`/>`にも置けます。

```glyph
path /> optimize
```

---

## `!`: 外部作用境界

```glyph
!write_log(event:Event):Receipt
!send(command:Command):Result
```

`!`はファイル、ネットワーク、GPIO、DB、時刻など、外部世界へ作用する境界です。具体的な実装はRust host adapterへ残します。

---

## 状態機械と時間制約

`machine`で初期状態、遷移関数、正常終端、異常終端を設計します。`?name(...)`では時相制約を宣言できます。

```glyph
?safe(*Input)=A(!auth >> !open)
```

Studioと生成物では、状態遷移と時相制約を別ビューで確認できます。

---

## 内部表現

`:=`ブロックは、既存の型検査・call graph・マクロ展開を再利用するため、コンパイラ内部では決定的なSSA/continuation形式へloweringします。

利用者向けの生成Rustでは内部helperを除去し、元の構造を直接復元します。

```text
Glyph := block
      ↓
検査用の純粋IR
      ↓
Typed design JSON / call graph
      ↓
Rust let bindings
```

Typed design JSONには次を保持します。

- binding名
- 推論型
- `expression` / `conditional`
- 元ソース行
- 元の右辺
- ラムダlowering
- Architecture / SymbolId / Rust TODO契約

---

## 記号一覧

| 記号 | 意味 |
|---|---|
| `system` | component接続 |
| `@` | コンパイル時マクロ |
| `*` | 積型 |
| `+` | 直和型 |
| `>` | Glyph実装の関数 |
| `~` | Rust実装の純粋TODO契約 |
| `!` | 外部作用境界 |
| `:=` | 一度だけ定義する中間値 |
| `>>` | 条件またはpatternと結果 |
| `/>` | 左から右への処理連結 |
| `|x| expr` | pipeline lambda |
| `?name` | 時相制約宣言 |
| `expr?` | Resultの失敗伝播 |
| `A / E / U / W` | 時相演算子 |

式中の等値比較は`==`を使います。単独の`=`は宣言と関数本体の区切りです。

---

## 生成物

Studioは生成先を自動的に決めます。

```text
.glyph/<source-stem>/
├── architecture.mmd
├── architecture-ir.json
├── execution.mmd
├── execution-ir.json
├── machine-<name>.mmd
├── temporal.mmd
├── source-map.json
├── index.md
├── typed-ast.json
├── generated.rs
├── host.generated.rs
└── manual.rs          # ~宣言がある場合。初回だけ作成
```

所有権:

```text
generated.rs       Glyph所有。再生成される
host.generated.rs  Glyph所有。再生成される
manual.rs          利用者所有。上書きされない
```

---

## 低水準CLI

`glyphc.py`はCIや外部ツール連携用です。通常の設計作業では`glyph.py`を使います。

```bash
python3 glyphc.py examples/function_block.glyph \
  -o build/generated.rs \
  --diagram-dir build/diagrams \
  --ast-json build/typed-design.json
```

---

## テスト

```bash
python3 -m unittest discover -s tests -v
cargo test --manifest-path demo/Cargo.toml
cargo test --manifest-path demo-system/Cargo.toml
```

CIでは次を検証します。

- `:=`の単一代入性
- 条件ブロックとvariant pattern
- `/>`とラムダ
- 中間値内の`?`伝播
- 生成Rustの`rustc`コンパイル
- `~`と`manual.rs`の保持
- Architecture / State / Time / source map
- 既存デモ、Cargo test、Clippy

---

## 詳細仕様

- `SKETCH_DESIGN.md` — 500文字設計スケッチ全体
- `PIPELINE_DESIGN.md` — `system`、`/>`、ラムダ
- `RUST_TODO.md` — `~` Rust TODO契約
- `LANGUAGE.md` — 基本文法
- `TEMPORAL_DESIGN.md` — 時相論理
- `examples/function_block.glyph` — `:=`を使ったアルゴリズム例

---

## 現在の制限

- `:=`は関数内の一度きりの定義であり、再代入はできない
- `:=`条件ブロックは最後に`_`fallbackを必要とする
- binding型の明示構文は未対応。右辺から推論する
- capturing closure、部分適用、複数引数pipeline lambdaは未対応
- standalone lambdaは未対応。ラムダは`/>`段で使う
- 文字列、配列、参照、lifetime、ジェネリック関数は未対応
- 計算量コメントは契約メタデータであり、自動証明しない
- `manual.rs`のシグネチャ不一致はRustコンパイルで検出する
- runtime `eval`は提供しない

## ライセンス

MIT License

# Glyph Rust

Glyphは、ソフトウェアの**構造・判断・状態・作用・時間制約・アルゴリズム骨格**を短いコードで記述し、同じ設計からStudio、Mermaid、型付き設計JSON、Rustを生成するDSLです。

詳細実装をすべてGlyphへ移すのではなく、人間とAIが確認すべき設計をGlyphへ残し、計算量やデータ構造まで作り込む処理は`~`でRustへ委譲します。

```text
自然言語・要求
      ↓
Glyphの設計モデル
├── Architecture
├── Data / Decision
├── State / Time
├── Algorithm skeleton
├── Raw preprocessor
└── Effect / Rust boundary
      ↓
Rust・Mermaid・型付き設計JSON
```

## 起動

通常利用は1コマンドです。

```bash
python3 glyph.py examples/function_block.glyph
```

Glyph Studioでは次を扱います。

- Glyphソースの編集と保存
- 自動再コンパイルと診断
- Architecture / State / Logic / Time
- 生成Rust、host adapter、`manual.rs`
- Typed AST / SymbolId / `:=` block / raw macro metadata
- 生成物一覧

## 10分で書くアルゴリズム骨格

```glyph
@MAX=100
@INPUT_TYPE=Command

system Planner
  input -> process
  process -> optimize
  optimize -> output

+INPUT_TYPE=Stop|Run(U)|Fault
+Error=Bad

>validate(x:U):U|Error=Ok(x)
~optimize(x:U):U # TODO: 計算量とデータ構造をRustで設計

>process(c:INPUT_TYPE):U|Error
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

この1ファイルから、次を生成します。

```text
Architecture       input → process → optimize → output
Logic              match → validate → normalize → optimize
Rust               型、純粋関数、let、Result伝播
Manual             optimizeの型安全なRust雛形
Design JSON        中間値、ラムダ、マクロ、SymbolId、source line
Preprocessor view  完全展開済みGlyphと展開対応表
```

---

## `@`: rawプリプロセッサ

既存の`@`は、Glyphソース全体で働くrawプリプロセッサです。`${NAME}`や`@define`は使いません。Cのobject-like macroと同じく、使用側には裸の識別子を書きます。

### 1行rawマクロ

```glyph
@MAX=100
@INPUT_TYPE=SensorInput
@EDGE=sensor -> ctl
@DECL=*INPUT_TYPE(value:U)
```

使用:

```glyph
DECL

system Controller
  EDGE

>clamp(x:U):U
  x>MAX >> MAX
  _ >> x
```

プリプロセス後:

```glyph
*SensorInput(value:U)

system Controller
  sensor -> ctl

>clamp(x:U):U
  x>100 >> 100
  _ >> x
```

置換は部分文字列ではなく、完全な識別子トークン単位です。

```glyph
@IN=Value

IN       # Valueへ展開
Input    # 展開しない
MIN      # 展開しない
```

### 複数行rawマクロ

```glyph
@NORMALIZE
  positive :=
    x<0 >> -x
    _ >> x

  limited :=
    positive>MAX >> MAX
    _ >> positive
@end
```

使用:

```glyph
>process(x:I):I
  NORMALIZE
  limited
```

呼出し行のインデントが展開本体へ加算されます。複数行マクロは行へ単独で置きます。

```glyph
result := NORMALIZE   # エラー
NORMALIZE /> encode  # エラー
```

### 大文字名を必須とする

rawマクロ名は次に一致しなければなりません。

```text
[A-Z][A-Z0-9_]*
```

```text
MAX             有効
INPUT_TYPE      有効
NORMALIZE_V2    有効
max             無効
InputType       無効
```

関数引数や局所値との暗黙衝突を減らすため、推奨ではなく構文規則として大文字を要求します。

### ASTマクロとの分離

引数付きの式マクロは従来どおり小文字名を使用できます。

```glyph
@MAX=100
@limit(x)=min(x,MAX)

>run(x:U):U=limit(x)
```

処理順は次です。

```text
raw @MAXを展開
      ↓
@limit(x)=min(x,100)をASTマクロとして解析
      ↓
limit(value)を式ASTとして展開
```

| 構文 | 種類 | 用途 |
|---|---|---|
| `@NAME=text` | 1行rawマクロ | 任意のGlyphソース断片 |
| `@NAME ... @end` | 複数行rawマクロ | 宣言や`:=`ブロック全体 |
| `@name(args)=expr` | ASTマクロ | 引数付きの式変換 |

### C同様に括弧を自動追加しない

rawマクロは文字列レベルのソース置換です。

```glyph
@NEXT=x+1
>f(x:I):I=NEXT*2
```

展開結果は次です。

```glyph
>f(x:I):I=x+1*2
```

`(x+1)*2`が必要なら定義側へ括弧を書きます。

```glyph
@NEXT=(x+1)
```

### コメント、入れ子、循環

`#`以降は展開しません。

```glyph
@MAX=100
>f():I=MAX # MAXは説明文として残る
```

rawマクロは再帰的に展開されます。

```glyph
@BASE=10
@LIMIT=BASE+5
```

循環は未使用でも拒否します。

```glyph
@A=B
@B=A
```

```text
raw macro cycle: A -> B -> A
```

展開深度、展開行数、展開文字数にも上限があります。

### プリプロセッサ生成物

```text
preprocessed.glyph
preprocessor-map.json
```

`preprocessed.glyph`は完全展開後のGlyphです。設計の正本は元の`.glyph`です。

`preprocessor-map.json`は、展開後の各行について次を記録します。

```json
{
  "expanded_line": 12,
  "source_line": 30,
  "macro_stack": ["NORMALIZE", "LIMIT_BRANCH"],
  "definition_lines": [3, 15]
}
```

診断、Semantic model、Architecture、Algorithm IR、Execution IR、Mermaidリンクは元の呼出し行へ戻されます。詳しい仕様は[`PREPROCESSOR.md`](PREPROCESSOR.md)を参照してください。

---

## `system`: 外側の構造

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

### 最終結果を直接選ぶガード関数

```glyph
+Kind=Negative|Zero|Positive

>classify(x:I):Kind
  x<0 >> Negative
  x==0 >> Zero
  _ >> Positive
```

上から最初に成立した節を返します。最後の`_`は必須の`else`です。

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

### 中間値を持つ`:=`ブロック

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

```text
name := expression

name :=
  condition >> expression
  _ >> expression

final-expression
```

`:=`は可変代入ではなく、一度だけ行う不変値定義です。

```glyph
value := first(input)
value := second(input) # エラー
```

分岐、variant pattern、`?`、`/>`、ラムダを右辺に置けます。

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

```glyph
>checked(x:U):U|Error
  value := validate(x)?
  Ok(value)
```

---

## `/>`: 左から右への処理連結

```glyph
value /> f /> g
```

は`g(f(value))`と同じ意味です。

```glyph
normalized :=
  value
  /> validate?
  /> convert
  /> encode
```

失敗を伝播する段には`?`を付けます。

---

## ラムダ

一度しか使わない短い局所変換は、pipeline lambdaで書けます。

```glyph
normalized :=
  value
  /> |x| x+1
  /> |x| min(x,MAX)
```

型を推論できない場合:

```glyph
value /> |x:U| x+1
```

現在のlambdaは、1引数・単一式・non-capturing・pure・`/>`内に限定しています。

| 状況 | 使用するもの |
|---|---|
| 一度しか使わない短い変換 | ラムダ |
| 値を次段へ渡すだけ | `/>` |
| 分岐の合流結果 | `:=` |
| 後続から再利用する値 | `:=` |
| 名前が設計上の意味を持つ節目 | `:=` |

---

## 再帰

```glyph
>sum(n:U):U
  n==0 >> 0
  _ >> n+sum(n-1)
```

単純な`parameter - constant`型自己再帰はTyped ASTで`structural`、その他の循環は`unchecked`として記録します。停止性の完全証明ではありません。

---

## `~`: 複雑なアルゴリズムをRustへ残す

```glyph
*Graph(nodes:U,edges:U)
*Path(cost:U)

~shortest_path(graph:Graph,start:U,goal:U):Path
  # TODO: Dijkstra/A*、O(E log V)、メモリ配置をRustで設計

>plan(graph:Graph,start:U,goal:U):Path
  path := shortest_path(graph,start,goal)
  path
```

| 記号 | 意味 | 実装場所 |
|---|---|---|
| `>` | Glyphで記述するロジック | Glyph |
| `~` | 複雑な純粋アルゴリズム | `manual.rs` |
| `!` | 通信、ファイル、GPIO等の外部作用 | host adapter |

Studioは初回だけ`.glyph/<source-stem>/manual.rs`へ型安全な雛形を作り、その後は上書きしません。

---

## `!`: 外部作用境界

```glyph
!read_sensor():Input
!write_motor(command:Command):Receipt
```

`!`は通信、GPIO、ファイル、DB、デバイスI/Oなど、外部世界への作用を表します。

---

## Source-level Logic view

StudioのLogicタブは、lowering後のcall graphではなく、元の`:=`ブロックからAlgorithm IRを生成します。rawマクロを使った箇所では、式本文は展開後の内容を表示し、source lineは元の呼出し行を指します。

```text
speed := match Command
        ↓
checked := validate? ──Err──→ exit
        ↓
normalized := λ min(n,100) → optimize [Rust]
        ↓
emitted := emit [effect]
        ↓
return
```

Logic viewは次を保持します。

- `:=`の順序と推論型
- 分岐条件、分岐値、variant binder
- `/>`のstage順序
- 展開後のラムダ式
- `~`と`!`の区別
- `?`からのErr経路
- 元Glyphのsource line

`__glyph_block_*`と`__glyph_lambda_*`は人間向けLogicへ表示しません。lowering後の構造は`execution-ir.json`と`execution.mmd`に残します。

詳細は[`ALGORITHM_IR.md`](ALGORITHM_IR.md)を参照してください。

---

## Studio

```bash
python3 glyph.py path/to/design.glyph
```

```text
Source editor
Automatic compile and diagnostics
Architecture
State
Logic
Time
Rust
Host
Manual
Typed AST
Symbols
Artifacts
```

Typed ASTには`raw_macros`と`preprocessor` metadataも含まれます。コンパイルエラー時もStudioは終了せず、最後に成功した生成物と現在の診断を保持します。

---

## 生成物

```text
.glyph/<source-stem>/
├── preprocessed.glyph
├── preprocessor-map.json
├── architecture.mmd
├── architecture-ir.json
├── logic.mmd
├── algorithm-ir.json
├── execution.mmd
├── execution-ir.json
├── machine-<name>.mmd
├── temporal.mmd
├── source-map.json
├── index.md
├── typed-ast.json
├── generated.rs
├── host.generated.rs
└── manual.rs
```

| ファイル | 対象 |
|---|---|
| `preprocessed.glyph` | rawマクロ完全展開後のソース |
| `preprocessor-map.json` | 展開行から呼出し行・定義行への対応 |
| `algorithm-ir.json` / `logic.mmd` | source-levelの`:=`、分岐、pipeline、lambda |
| `execution-ir.json` / `execution.mmd` | compiler lowering後のcall graph |
| `source-map.json` | 各設計viewから元Glyph行への逆引き |

---

## 記号一覧

| 記法 | 意味 |
|---|---|
| `@NAME=text` | 1行rawプリプロセッサマクロ |
| `@NAME ... @end` | 複数行rawプリプロセッサマクロ |
| `@name(args)=expr` | AST式マクロ |
| `system` | component接続 |
| `*` | 積型 |
| `+` | 直和型 |
| `>` | Glyph実装の純粋関数 |
| `~` | Rust実装の純粋関数契約 |
| `!` | 外部作用境界 |
| `:=` | 一度だけ定義する中間値 |
| `>>` | ガード条件から値 |
| `/>` | 左から右への処理連結 |
| `|x| expression` | pipeline lambda |
| `expression?` | Result失敗伝播 |
| `?name(...)=formula` | 時相制約 |

---

## 設計文書

- [`PREPROCESSOR.md`](PREPROCESSOR.md) — rawプリプロセッサ、展開規則、source map
- [`SKETCH_DESIGN.md`](SKETCH_DESIGN.md) — 500文字設計スケッチ
- [`PIPELINE_DESIGN.md`](PIPELINE_DESIGN.md) — `system`、`/>`、ラムダ
- [`RUST_TODO.md`](RUST_TODO.md) — `~`と`manual.rs`
- [`ALGORITHM_IR.md`](ALGORITHM_IR.md) — source-level Algorithm IRとLogic view
- [`LISP_CORE.md`](LISP_CORE.md) — 関数値、AST macro、再帰
- [`LANGUAGE.md`](LANGUAGE.md) — コア言語仕様

---

## CI・低水準利用

```bash
python3 glyphc.py design.glyph --check
python3 glyphc.py design.glyph --diagram-dir .glyph/design
python3 -m unittest tests.test_preprocessor -v
python3 -m unittest discover -s tests -v
cargo test --manifest-path demo/Cargo.toml
cargo test --manifest-path demo-system/Cargo.toml
```

---

## 現在の制限

- rawマクロはhygienicではない
- 条件付きコンパイル、`include`、トークン連結、可変長引数は未対応
- 複数行rawマクロは式の一部分へ埋め込めない
- capturing closure、部分適用、複数引数pipeline lambdaは未対応
- standalone lambdaは未対応
- `:=`は単一代入であり、可変変数とループ文は提供しない
- 文字列、配列、参照、lifetime、ジェネリック関数は未対応
- 再帰metadataは停止性の完全証明ではない
- `manual.rs`のシグネチャ変更はRustコンパイルで検出する
- 実機の外部作用はRust host adapterへ実装する
- runtime `eval`は提供しない

## License

MIT License

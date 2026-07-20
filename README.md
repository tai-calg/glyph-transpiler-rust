# Glyph

Glyphは、型・純粋計算・状態遷移・作用境界・時相制約を一つの短いファイルへ記述し、Rustと設計ビューを同時に生成するシステム設計DSL。

通常利用で覚えるコマンドは一つだけ。

```bash
python3 glyph.py examples/system_controller.glyph
```

このコマンドはGlyph Studioを起動する。

```text
Glyph source
   ↓
Glyph Studio
├── ソース編集
├── 構文・型検査
├── 自動再コンパイル
├── Rust生成
├── Typed AST / SymbolId表示
├── 実行フロー表示
├── machine状態遷移表示
├── 時相制約表示
└── 生成物一覧
```

ブラウザ上のStudioは同じPythonプロセス内で動作する。別々の`compile`、`watch`、`diagram`、`repl`コマンドを切り替える必要はない。

## Glyph Studio

```bash
python3 glyph.py path/to/controller.glyph
```

起動後に利用できる画面:

| View | 内容 |
|---|---|
| Overview | 関数、machine、時相制約、Symbol数、診断 |
| Machine | 初期状態、遷移、正常終端、異常終端 |
| Flow | 関数、分岐、作用境界、戻り値の実行構造 |
| Temporal | 時相制約と生成モニタ |
| Rust | 生成されたロジック側Rust |
| Host | 作用境界側Rust |
| AST | 型付き式木と再帰情報 |
| Symbols | `SymbolId`、種類、名前、型 |
| Artifacts | 自動生成された全ファイル |

ソースを保存すると、同じプロセス内で再解析・再生成される。外部エディタによる変更も自動検出する。

生成物は自動的に次へ配置する。

```text
<source directory>/.glyph/<source stem>/
├── generated.rs
├── host.generated.rs
├── typed-ast.json
├── execution.mmd
├── execution-ir.json
├── source-map.json
├── temporal.mmd
├── machine-*.mmd
└── index.md
```

生成先の指定は通常不要。

## 最小例

```glyph
@LOW=10.0
@HOT=80.0
@MAX=1000
@BAD=!finite(v)|!finite(t)|v<0.0
@BLOCK=s.v<LOW|s.t>HOT|s.r==0

*S(v,t:F,r:U)
+C=Stop|Run(U)
+Error=BadSensor|Actuator
*Receipt(c:C)
*Observation(send,ack,closed,auth,beat,stable:B)

>decode(*S):S|Error
  BAD >> Err(BadSensor)
  _ >> Ok(S(v,t,r))

>cmd(s:S):C
  BLOCK >> Stop
  _ >> Run(min(s.r,MAX))

!exec(c:C):Receipt|Error=Ok(Receipt(c))
>run(*S):Receipt|Error=exec(cmd(decode(v,t,r)?))

?ack(*Observation)=A(send>>E 5s ack)
?safe(*Observation)=A(!auth>>closed)
?wait(*Observation)=closed W auth
?live(*Observation)=AE 1s beat
?conv(*Observation)=EA stable
```

## 基本文法

| Glyph | 意味 | Rust |
|---|---|---|
| `*Name(...)` | 積型 | `struct` |
| `+Name=...` | 直和型 | `enum` |
| `>name(...)` | 純粋関数 | `fn` |
| `!name(...)` | 作用境界 | `crate::host` |
| `T|E` | 成功または失敗 | `Result<T,E>` |
| `condition >> value` | 値を返すガード | `if` / `else` |
| `?name(...)=formula` | 時相制約 | runtime monitor |
| `expression?` | 失敗伝播 | Rust `?` |
| `==` | 等値比較 | `==` |

`=`は宣言・定義の区切りにだけ使う。

## 型

短縮型:

```text
F -> f32
D -> f64
U -> u16
I -> i32
B -> bool
T|E -> Result<T,E>
```

同じ型を持つ名前はまとめられる。

```glyph
*Point(x,y:F)
```

## 純粋関数を値として渡す

```glyph
>inc(x:U):U=x+1
>apply(f:Fn<U,U>,x:U):U=f(x)
>run(x:U):U=apply(inc,x)
```

`Fn<U,U>`は、`U`を受け取り`U`を返す純粋関数の型。

作用境界`!`と、推移的に作用境界へ到達する関数は関数値にできない。

## 再帰

```glyph
>sum(n:U):U
  n==0 >> 0
  _ >> n+sum(n-1)
```

構造的に減少する自己再帰はTyped AST上で`structural`と記録する。

```glyph
>loop(x:U):U=loop(x)
```

停止性を確認できない再帰も受理し、`unchecked`と記録する。コンパイラは拒否せず、停止性も保証しない。

## ASTコンパイル時マクロ

```glyph
@twice(f,x)=f(f(x))

>inc(x:U):U=x+1
>run(x:U):U=twice(inc,x)
```

関数形式のマクロは文字列ではなく式木を置換する。引数数、循環、展開深度を検査する。

定数・共通式には既存の単語マクロも使える。

```glyph
@MAX=1000
```

## machine

```glyph
+Mode=Idle|Running|Stopping|Faulted

*System(mode:Mode,sequence:U)
*Input(stop,fault:B)

>step(state:System,input:Input):System
  input.fault >> System(Faulted,state.sequence+1)
  input.stop >> System(Stopping,state.sequence+1)
  _ >> System(Running,state.sequence+1)

machine Controller(state:System,input:Input)
  select=state.mode
  init=System(Idle,0)
  next=step(state,input)
  success=Stopping
  failure=Faulted
```

Studioはこの宣言から初期状態、遷移、正常終端、異常終端を表示する。

## 時相論理

| Glyph | 意味 |
|---|---|
| `!P` | 否定 |
| `P & Q` | 論理積 |
| `P | Q` | 論理和 |
| `P >> Q` | 含意 |
| `A P` | 常にP |
| `E P` | いつかP |
| `E 500ms P` | 500ms以内にP |
| `P U Q` | strong until |
| `P W Q` | weak until |
| `AE P` | 常に、いつかP |
| `EA P` | いつか、以後常にP |

例:

```glyph
?ack(send,ack:B)=A(send>>E 500ms ack)
```

有限トレースでは`Satisfied`、`Violated`、`Pending`の3値で評価する。

## 低水準コンパイラ

`glyphc.py`はCI、生成物固定、外部ツール統合向けの低水準インターフェースとして残す。通常の設計・編集では`glyph.py`だけを使う。

```bash
python3 glyphc.py input.glyph --check
```

## テスト

```bash
python3 -m unittest discover -s tests -v
cargo test --manifest-path demo/Cargo.toml
cargo test --manifest-path demo-system/Cargo.toml
```

## 詳細仕様

- [LANGUAGE.md](LANGUAGE.md)
- [TEMPORAL_DESIGN.md](TEMPORAL_DESIGN.md)
- [VARIANT_PATTERNS.md](VARIANT_PATTERNS.md)
- [LISP_CORE.md](LISP_CORE.md)
- [EXECUTION_STRUCTURE_DESIGN.md](EXECUTION_STRUCTURE_DESIGN.md)

## ライセンス

MIT License

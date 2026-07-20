# Glyph Rust

Glyphは、ソフトウェアの外側の構造と内側のロジックを短いコードで描き、Studio、Mermaid、型付き設計JSON、Rustへ同時展開するDSLです。

## 起動

通常利用は1コマンドだけです。

```bash
python3 glyph.py examples/door_sketch.glyph
```

Glyph Studioの同一プロセス内で、編集、保存、検査、Architecture、State、Logic、Time、Rust、AST、Symbolを扱います。

## 500文字スケッチ

```glyph
system Door
  sensor -> ctl
  panel -> ctl
  ctl -> lock
  ctl -> log

@MAX=1000
*In(open,auth,stop:B,value:U)
+C=Stop|Run(U)
+Error=Bad

>validate(i:In):In|Error=Ok(i)
>command(n:U):C|Error=Ok(Run(n))

>ctl(i:In):C|Error=
  i
  /> validate?
  /> |x| x.value
  /> |n| min(n,MAX)
  /> command

!lock(c:C):B=true
!log(c:C):B=true

?safe(*In)=A(!auth >> !open)
```

この1ファイルから次を生成します。

```text
Architecture  sensor/panel -> ctl -> lock/log
State         machineの初期状態・遷移・正常終端・異常終端
Logic         validate -> lambda -> lambda -> command
Time          未認可時にopenを禁止
Rust          型・純粋関数・effect境界・時相monitor
```

## Architecture

1接続を1行で書きます。

```glyph
system Door
  sensor -> ctl
  panel -> ctl
  ctl -> lock
  ctl -> log
```

component名は同名宣言へ自動bindingされます。

```text
>name  -> function
!name  -> effect
型name -> data
未定義 -> external
```

## `/>`パイプライン

`/>`は左から右へ処理を連結します。

```glyph
value /> f /> g
```

は次と同じ意味です。

```glyph
g(f(value))
```

失敗を伝播する段には既存の`?`を付けます。

```glyph
value /> validate? /> decide
```

## ラムダ

パイプライン内で、一度しか使わない純粋な局所変換を書けます。

```glyph
value
/> |x| x+1
/> |x| min(x,MAX)
```

現在のラムダは、1引数・単一式・non-capturing・純粋に限定しています。前段の値から引数型を推論し、必要なら明示できます。

```glyph
value /> |x:U| x+1
```

外側の実行時変数をcaptureするラムダや、effectへ到達するラムダは拒否します。

## 記号

| 記号 | 意味 |
|---|---|
| `system` | component接続 |
| `@` | コンパイル時マクロ |
| `*` | 積型 |
| `+` | 直和型 |
| `>` | 純粋関数 |
| `!` | 外部作用境界 |
| `>>` | ガードの条件と結果 |
| `/>` | 左から右への処理連結 |
| `|x| expr` | pipeline lambda |
| `?name` | 時相制約宣言 |
| `expr?` | Resultの失敗伝播 |
| `A / E / U / W` | 時相演算子 |

型位置の短縮型は次です。

```text
F -> f32
D -> f64
U -> u16
I -> i32
B -> bool
T|E -> Result<T,E>
```

式中の等値比較は`==`を使い、単独の`=`は宣言・定義の区切りだけに使います。

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
└── host.generated.rs
```

## 詳細仕様

- `SKETCH_DESIGN.md` — 500文字設計スケッチ全体
- `PIPELINE_DESIGN.md` — `system`、`/>`、ラムダの実装仕様
- `LANGUAGE.md` — 言語仕様
- `TEMPORAL_DESIGN.md` — 時相論理設計

## CI・低水準利用

`glyphc.py`はCIや外部ツール連携用です。通常の設計作業では`glyph.py`を使います。

```bash
python3 -m unittest discover -s tests -v
cargo test --manifest-path demo/Cargo.toml
cargo test --manifest-path demo-system/Cargo.toml
```

## 現在の制限

- capturing closure、部分適用、複数引数pipeline lambdaは未対応
- standalone lambdaは未対応。ラムダは`/>`段で使う
- 文字列、配列、参照、lifetime、ジェネリック関数は未対応
- 実機の外部作用はRust host adapterへ実装する
- runtime `eval`は提供しない

## ライセンス

MIT License

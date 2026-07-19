# Glyph Rust

頻出概念を一つの記号へ圧縮し、短いDSLから通常のRustコードを生成する依存ゼロの小型トランスパイラ。

## 最上位目的

> 自分が頻繁に使う概念を、一つの記号で一意に表現する。

| 記号 | 意味 | Rustへの展開 |
|---|---|---|
| `@` | 式中の単語マクロ | 識別子トークンを式へ展開 |
| `*` | 積型。複数の値を同時に持つ | `struct` |
| `+` | 直和型。候補のうち一つを取る | `enum` |
| `>` | 純粋な変換 | `fn` |
| `!` | 外部作用との境界 | `crate::host::<name>` |
| `R<T,E>` | 成功または失敗 | `Result<T,E>` |
| `?` | 失敗の早期返却 | Rustの`?` |
| `|` / `&` | 論理和 / 論理積 | `||` / `&&` |

## 単語マクロ

```text
@LOW=10
@HOT=80
@MAX=1000
@BLOCK=s.v<LOW|s.t>HOT|s.r=0
@PIPE=exec(cmd(decode(v,t,r)?))
```

使用:

```text
>cmd(s:S):C
  BLOCK => Stop
  _ => Run(min(s.r,MAX))

>run(v:f32,t:f32,r:u16):R<Receipt,E>=PIPE
```

マクロは文字列部分一致ではなく、式lexerが生成した完全一致の識別子トークンだけを置換する。

```text
@R=1
```

この定義は`R`を置換するが、`Receipt`は変更しない。置換式は括弧で囲んで解析するため、`@NEXT=x+1`を`NEXT*2`で使うと`(x+1)*2`になる。

実装済みの検査:

- 重複定義
- 空または不正な置換式
- 直接・間接循環
- 宣言名・enum variant名との衝突
- 展開深さ64超過
- 4096トークン超過

マクロは現在、**式だけ**を置換する。型マクロと引数付きマクロには未対応。

## 最短実行

必要環境:

- Python 3.10以上
- 生成したRustデモをビルドする場合のみCargo

```bash
python3 run.py
```

処理:

1. `examples/controller.glyph`を解析する
2. 単語マクロを展開する
3. `demo/src/generated.rs`を再生成する
4. Cargoが存在すれば`cargo test`を実行する
5. テスト成功後にデモを実行する

変換だけを実行:

```bash
python3 glyphc.py examples/controller.glyph -o generated.rs
```

構文検査だけを実行:

```bash
python3 glyphc.py examples/controller.glyph --check
```

Python側テスト:

```bash
python3 -m unittest discover -s tests -v
```

## 入力例

```text
@LOW=10
@HOT=80
@MAX=1000
@BAD=!finite(v)|!finite(t)|v<0
@BLOCK=s.v<LOW|s.t>HOT|s.r=0
@PIPE=exec(cmd(decode(v,t,r)?))

*S(v:f32,t:f32,r:u16)
+C=Stop|Run(u16)
+E=BadSensor|Actuator
*Receipt(c:C)

>decode(v:f32,t:f32,r:u16):R<S,E>
  BAD => Err(BadSensor)
  _ => Ok(S(v,t,r))

>cmd(s:S):C
  BLOCK => Stop
  _ => Run(min(s.r,MAX))

!exec(c:C):R<Receipt,E>
>run(v:f32,t:f32,r:u16):R<Receipt,E>=PIPE
```

コメントと空行を除くと18行、空白を除くと356文字。生成されるRustは39実コード行、空白を除くと544文字。

## 外部作用の扱い

DSL内の`!exec(...)`は、外部作用のシグネチャだけを宣言する。実装は`demo/src/host.rs`へ置く。

```rust
pub fn exec(c: C) -> Result<Receipt, E> {
    Ok(Receipt { c })
}
```

これにより、判断ロジックとGPIO、UART、CAN、ファイルI/Oなどを分離できる。

## ディレクトリ

```text
glyph-rust/
├── glyphc.py                 CLI
├── glyph/compiler.py         macro / lexer / parser / AST / Rust generator
├── examples/controller.glyph DSL入力例
├── demo/
│   ├── Cargo.toml
│   └── src/
│       ├── generated.rs      生成物
│       ├── host.rs           外部作用
│       └── main.rs           実行例とRustテスト
├── tests/                    Pythonテスト
├── LANGUAGE.md               文法仕様
├── DESIGN.md                 設計判断
└── run.py                    再生成・検査・実行
```

## 現在の制限

- 文字列リテラル、配列、ループ、参照、ライフタイム、ジェネリック関数は未対応
- 単語マクロは式専用で、引数を取らない
- 型検査はRustコンパイラへ委譲する
- `!`で宣言した関数は`crate::host`に実装する必要がある
- 生成先はRust 2021 Editionを想定する

## ライセンス

MIT License

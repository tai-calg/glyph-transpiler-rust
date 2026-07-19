# Glyph Rust

頻出概念を短い記号へ圧縮し、短いDSLから通常のRustコードを生成する依存ゼロの小型トランスパイラ。

## 最上位目的

> 自分が頻繁に使う概念を、構文位置から一意に読める記号で表現する。

| 記号 | 意味 | Rustへの展開 |
|---|---|---|
| `@` | 式中の単語マクロ | 識別子トークンを式へ展開 |
| `*` | 積型。複数の値を同時に持つ | `struct` |
| `+` | 直和型。候補のうち一つを取る | `enum` |
| `>` | 純粋な変換 | `fn` |
| `!` | 外部作用との境界 | `crate::host::<name>` |
| 型位置の `T|E` | 成功型または失敗型 | `Result<T,E>` |
| ガード行の `>>` | 条件と結果の区切り | `if` / `else` |
| トップレベルの `?` | 時相制約 | Rustモニタ |
| 式末尾の `?` | 失敗の早期返却 | Rustの`?` |
| 式位置の `|` / `&` | 論理和 / 論理積 | `||` / `&&` |

`|`と`?`は構文位置で区別する。型シグネチャではResult型、式では論理和、直和型宣言ではvariant区切りになる。トップレベルの`?name(...)=...`は時相制約、式末尾の`?`は失敗伝播になる。

時相制約の文法、有限トレース意味論、生成モニタ、省メモリ化計画は[`TEMPORAL_DESIGN.md`](TEMPORAL_DESIGN.md)を参照。

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
  BLOCK>>Stop
  _>>Run(min(s.r,MAX))

>run(*S):Receipt|E=PIPE
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
2. 時相制約を抽出し、短縮構文と単語マクロを展開する
3. `demo/src/generated.rs`と`demo/src/host.generated.rs`を再生成する
4. Cargoが存在すれば`cargo test`を実行する
5. テスト成功後にデモを実行する

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

*S(v,t:f,r:u)
+C=Stop|Run(u)
+E=BadSensor|Actuator
*Receipt(c:C)
*O(send,ack,closed,auth,beat,stable:b)

>decode(*S):S|E
  BAD>>Err(BadSensor)
  _>>Ok(S(v,t,r))

>cmd(s:S):C
  BLOCK>>Stop
  _>>Run(min(s.r,MAX))

!exec(c:C):Receipt|E=Ok(Receipt(c))
>run(*S):Receipt|E=PIPE

?ack(*O)=□(send>>◇5s ack)
?safe(*O)=□(!auth>>closed)
?wait(*O)=closed W auth
```

短縮構文は従来文法へ展開してから解析する。

```text
*S(v,t:f,r:u)       -> *S(v:f32,t:f32,r:u16)
>run(*S):Receipt|E  -> >run(v:f32,t:f32,r:u16):R<Receipt,E>
BLOCK>>Stop          -> BLOCK=>Stop
```

従来の`R<T,E>`とガード矢印`=>`も互換構文として使用できる。

## 時相制約

```glyph
?ack(*O)=□(send>>◇5s ack)
```

は、すべての`send`について5秒以内の`ack`を要求するRustモニタを生成する。

生成モニタは次の3値を返す。

```rust
TemporalVerdict::Satisfied
TemporalVerdict::Violated
TemporalVerdict::Pending
```

API:

```rust
monitor.step(at_ms, ...);
monitor.verdict();
monitor.finish();
monitor.reset();
```

第1版は意味論を検査する全履歴参照実装であり、長時間稼働向けの逐次モニタは次段階で追加する。

## 外部作用の扱い

`!name(args):Ret`は外部作用の境界だけを宣言する。`=expression`を付けると、試作実装を`host.generated.rs`へ生成する。

```text
!exec(c:C):Receipt|E=Ok(Receipt(c))
```

生成:

```rust
pub fn exec(c: C) -> Result<Receipt, E> {
    Ok(Receipt { c })
}
```

実機接続では`host.rs`をGPIO、UART、CANなどのアダプターへ差し替える。

## ディレクトリ

```text
glyph-rust/
├── glyphc.py                 CLI
├── glyph/compiler.py         lexer / parser / AST / Rust generator
├── glyph/syntax.py           短縮構文展開
├── glyph/temporal.py         時相式AST / parser / spec抽出
├── glyph/temporal_codegen.py 時相Rustモニタ生成
├── glyph/artifacts.py        logic / host生成
├── examples/controller.glyph DSL入力例
├── demo/
│   ├── Cargo.toml
│   └── src/
│       ├── generated.rs      ロジック・モニタ生成物
│       ├── host.generated.rs 試作用作用実装
│       ├── host.rs           実機アダプター差替点
│       └── main.rs           実行例とRustテスト
├── tests/                    Pythonテスト
├── LANGUAGE.md               文法仕様
├── COMPACT_SYNTAX.md         短縮構文仕様
├── DESIGN.md                 全体設計
├── TEMPORAL_DESIGN.md        時相制約設計
└── run.py                    再生成・検査・実行
```

## 現在の制限

- 文字列リテラル、配列、ループ、参照、ライフタイム、ジェネリック関数は未対応
- 単語マクロは式専用で、引数を取らない
- 型検査はRustコンパイラへ委譲する
- 実機の外部作用は`crate::host`に実装する
- 時相モニタ第1版は全観測を保持する参照実装
- `X`、過去演算子、ID付き要求応答相関は未対応
- 生成先はRust 2021 Editionを想定する

## ライセンス

MIT License

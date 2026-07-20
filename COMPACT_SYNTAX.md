# Compact Glyph syntax

Glyphは表面構文を内部文法へ正規化してからASTを解析する。正規化は行数を変えないため、構文エラーの行番号は元の`.glyph`ファイルと一致する。

```glyph
*S(v,t:F,r:U)
>decode(*S):S|Error
  BAD>>Err(BadSensor)
  _>>Ok(S(v,t,r))
```

| 表面構文 | 内部表現 |
|---|---|
| `v,t:F` | `v:f32,t:f32` |
| 関数引数の `*S` | 積型`S`の全フィールド |
| 型位置の `T|E` | `R<T,E>` |
| ガード行の `condition>>expression` | `condition=>expression` |
| `F` / `D` | `f32` / `f64` |
| `U` / `I` / `B` | `u16` / `i32` / `bool` |
| 時相式の `A` / `E` | 内部ASTのAlways / Eventually |
| `EA stable` | `E(A stable)` |

例えば、

```glyph
*S(v,t:F,r:U)
>run(*S):Receipt|Error=PIPE
```

は次へ展開される。

```glyph
*S(v:f32,t:f32,r:u16)
>run(v:f32,t:f32,r:u16):R<Receipt,Error>=PIPE
```

`|`は文脈で区別する。

- 型シグネチャ最上位の`T|E`: Result型
- 式位置の`a|b`: 論理和
- 直和型宣言の`+A=X|Y`: variant区切り

`=`は宣言・定義の区切りだけに使う。式中の等値比較は`==`と書く。

```glyph
@ZERO=x==0
>same(x,y:U):B
  x==y>>true
  _>>false
```

旧短縮型`f/d/u/i/b`、旧時相記号`□/◇`、式中の単独`=`は受理しない。エラーには対応する新構文を表示する。

時相演算子列とオペランドの間には空白または`(`を置く。

```text
EA stable   # E(A stable)
EA(stable)  # E(A stable)
EAstable    # EAstableという識別子
```

従来の`R<T,E>`とガード矢印`=>`は内部互換構文として使用できる。`T?E`と`T/E`は受理しない。

型の一文字短縮は型位置だけで有効。同名のユーザー定義型が存在する場合はユーザー定義型を優先する。

ガード関数のフォールバックは省略しない。最後の分岐は必ず`_>>expression`と明示する。

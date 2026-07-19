# Compact Glyph syntax

Glyphは、短縮表記を従来文法へ展開してから解析する。既存文法はそのまま使用できる。

```glyph
*S(v,t:f,r:u)
>decode(*S):S?E
  BAD=>Err(BadSensor)
  Ok(S(v,t,r))
```

| 短縮表記 | 展開後 |
|---|---|
| `v,t:f` | `v:f,t:f` |
| 関数引数の `*S` | 積型`S`の全フィールド |
| `T?E` | `R<T,E>` |
| `f` / `d` | `f32` / `f64` |
| `u` / `i` / `b` | `u16` / `i32` / `bool` |
| ガード末尾の裸式 | `_ => expression` |

例えば、

```glyph
*S(v,t:f,r:u)
>run(*S):Receipt?E=PIPE
```

は次へ展開される。

```glyph
*S(v:f32,t:f32,r:u16)
>run(v:f32,t:f32,r:u16):R<Receipt,E>=PIPE
```

展開では行数を変えないため、構文エラーの行番号は元の`.glyph`ファイルと一致する。型の一文字短縮は型位置でのみ有効で、同名のユーザー定義型が存在する場合はユーザー定義型を優先する。

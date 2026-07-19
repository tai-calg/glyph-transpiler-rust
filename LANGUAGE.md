# Glyph Language 0.2

## 1. 設計原則

1. 記号の意味は構文位置から一意に決まる。
2. DSLは型、変換、失敗、外部作用の境界だけを記述する。
3. 所有権、ドライバ、非同期処理などRust固有の詳細はホスト側へ残す。
4. 単語マクロは文字列部分一致ではなく、識別子トークン完全一致で展開する。
5. 短縮構文とマクロを展開してからASTへ解析し、通常のRustを生成する。

## 2. 単語マクロ

### 構文

```text
@NAME=expression
```

例:

```text
@LOW=10
@MAX=1000
@BLOCK=s.v<LOW|s.t>80|s.r=0
@LOWER=min

>cap(x:u16):u16=LOWER(x,MAX)
>cmd(s:S):C
  BLOCK>>Stop
  _>>Run(s.r)
```

意味:

- `NAME`は有効な識別子でなければならない。
- 置換対象は式中の完全一致した識別子トークンだけである。
- `@R=1`は`R`を置換するが、`Receipt`の一部は置換しない。
- マクロはファイル全体で有効であり、宣言順に依存しない。
- マクロ本体から別のマクロを参照できる。
- マクロ本体は式であり、型またはトップレベル宣言の置換には使わない。
- 引数付きマクロは未対応である。

### 優先順位

各置換式は構文上の括弧で囲んで展開する。

```text
@NEXT=x+1
>f(x:i32):i32=NEXT*2
```

生成:

```rust
pub fn f(x: i32) -> i32 {
    (x + 1) * 2
}
```

### 検査

以下をコンパイルエラーにする。

- 同名マクロの重複
- 空の置換式
- 文法的に不正な置換式
- マクロの直接・間接循環
- 宣言名またはenum variant名との衝突
- 展開深さ64超過
- 一式あたり4096展開トークン超過

循環例:

```text
@A=B
@B=A
```

エラー:

```text
macro cycle: A -> B -> A
```

マクロ名には大文字を推奨する。小文字も使用できるが、ローカル変数やフィールド名と一致すれば、その識別子も置換対象になる。

## 3. 宣言

### 積型

```text
*Point(x:f32,y:f32)
```

短縮:

```text
*Point(x,y:f)
```

生成:

```rust
pub struct Point {
    pub x: f32,
    pub y: f32,
}
```

### 直和型

```text
+State=Idle|Run(u)|Fault{code:u8,msg:S}
```

生成:

```rust
pub enum State {
    Idle,
    Run(u16),
    Fault { code: u8, msg: String },
}
```

### 型別名

```text
=Output=u|E
```

生成:

```rust
pub type Output = Result<u16, E>;
```

### 純粋関数

単一式:

```text
>double(x:u):u=x*2
```

ガード節:

```text
>sign(x:i):i
  x<0>>-1
  x=0>>0
  _>>1
```

`>>`はガードの条件と結果を区切る。`_`は最後に一つだけ必要である。従来の`=>`も互換構文として受理する。

### 外部作用境界

```text
!send(x:u8):u8|E
```

呼出しは次へ展開される。

```rust
crate::host::send(x)
```

`=expression`を付けると試作実装を生成する。

```text
!send(x:u8):u8|E=Ok(x)
```

## 4. 型

長形式:

```text
u8 u16 u32 u64
 i8 i16 i32 i64
f32 f64 bool String
R<T,E>  -> Result<T,E>
O<T>    -> Option<T>
V<T>    -> Vec<T>
S       -> String
```

短縮表記では、型位置に限って次も使える。

```text
T|E       -> R<T,E> -> Result<T,E>
f d u i b -> f32 f64 u16 i32 bool
```

`|`は文脈によって一意に解釈する。

- 型シグネチャ最上位の`T|E`: Result型
- 式中の`a|b`: 論理和
- 直和型宣言の`+A=X|Y`: variant区切り

`?`は型記号として使わず、式末尾の失敗伝播だけを表す。旧候補の`T?E`と`T/E`は受理しない。従来の`R<T,E>`は引き続き使用できる。

ユーザー定義型が`S`、`f`、`u`などの短縮名と一致する場合は、ユーザー定義型を優先する。

### 積型引数展開

積型のfield rowは関数引数へ展開できる。

```text
*S(v,t:f,r:u)
>decode(*S):S|E
```

展開:

```text
*S(v:f32,t:f32,r:u16)
>decode(v:f32,t:f32,r:u16):R<S,E>
```

## 5. 式

対応済み:

```text
name
123
12.5
true false
f(x,y)
x.field
expr?
!expr
-expr
a+b a-b a*b a/b
a<b a>b a<=b a>=b a=b a!=b
cond1|cond2
cond1&cond2
```

演算子優先順位は高い順に以下。

```text
postfix: () . ?
unary:   ! -
product: * /
sum:     + -
compare: = != < > <= >=
and:     &
or:      |
```

## 6. 組込み関数

```text
Ok(x)
Err(e)
Some(x)
None
min(a,b)
max(a,b)
finite(x)
```

展開:

```text
min(a,b)    -> std::cmp::min(a,b)
max(a,b)    -> std::cmp::max(a,b)
finite(x)   -> x.is_finite()
```

## 7. 文法概要

短縮文法:

```text
program          := (macro | declaration)*
macro            := "@" Name "=" expr
declaration      := product | sum | alias | function | extern
product          := "*" Name "(" compact-fields? ")"
sum              := "+" Name "=" variant ("|" variant)*
alias            := "=" Name "=" compact-type
function         := ">" signature ("=" expr | NEWLINE compact-guard+)
extern           := "!" signature ("=" expr)?
signature        := Name "(" compact-params? ")" ":" compact-type
compact-type     := type | type "|" type
compact-guard    := INDENT (expr | "_") ">>" expr
```

短縮展開後の既存文法:

```text
guard            := INDENT (expr | "_") "=>" expr
result-type      := "R" "<" type "," type ">"
```

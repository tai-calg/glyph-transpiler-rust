# Glyph Language 0.3

## 1. 設計原則

1. 記号の意味は構文位置から一意に決まる。
2. 型、純粋計算、状態遷移、作用境界、実行履歴制約を記述する。
3. 所有権、時計、ドライバ、非同期処理、違反後の復旧はRustホスト側へ残す。
4. 型短縮は大文字、値識別子は通常小文字として視覚的に区別する。
5. `=`は宣言・定義、`==`は等値比較に限定する。
6. 時相論理の表面構文はASCIIで入力できる形にする。

## 2. 単語マクロ

```glyph
@NAME=expression
```

例:

```glyph
@LOW=10
@MAX=1000
@BLOCK=s.v<LOW|s.t>80|s.r==0
@LOWER=min

>cap(x:u16):u16=LOWER(x,MAX)
```

- 置換対象は完全一致した識別子トークンだけ
- ファイル全体で有効
- 別のマクロを参照可能
- 式専用であり、型や宣言は置換しない
- 引数付きマクロは未対応
- `A`と`E`は時相演算子名として予約され、マクロ名には使用できない

以下を拒否する。

- 重複
- 空または不正な式
- 直接・間接循環
- 宣言名・variant名との衝突
- 展開深さ64超過
- 4096トークン超過

## 3. 宣言

### 積型

```glyph
*Point(x,y:F)
```

```rust
pub struct Point {
    pub x: f32,
    pub y: f32,
}
```

### 直和型

```glyph
+State=Idle|Run(U)|Fault{code:u8,msg:S}
```

```rust
pub enum State {
    Idle,
    Run(u16),
    Fault { code: u8, msg: String },
}
```

### 型別名

```glyph
=Output=U|Error
```

```rust
pub type Output = Result<u16, Error>;
```

### 純粋関数

単一式:

```glyph
>double(x:U):U=x*2
```

ガード:

```glyph
>sign(x:I):I
  x<0>>-1
  x==0>>0
  _>>1
```

`_`は最後に一つだけ必要。`=>`は内部互換構文として受理する。

### 外部作用境界

```glyph
!send(x:u8):u8|Error
```

呼出し:

```rust
crate::host::send(x)
```

試作実装:

```glyph
!send(x:u8):u8|Error=Ok(x)
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

短縮形式:

```text
F -> f32
D -> f64
U -> u16
I -> i32
B -> bool
T|E -> Result<T,E>
```

旧短縮型`f/d/u/i/b`は受理しない。同名のユーザー定義型が存在する場合はユーザー定義型を優先する。

積型のfield rowは関数引数へ展開できる。

```glyph
*S(v,t:F,r:U)
>decode(*S):S|Error
```

内部展開:

```text
*S(v:f32,t:f32,r:u16)
>decode(v:f32,t:f32,r:u16):R<S,Error>
```

## 5. 式

対応形:

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
a<b a>b a<=b a>=b a==b a!=b
cond1|cond2
cond1&cond2
```

単独`=`は式演算子ではない。等値比較は`==`だけを使う。

優先順位:

```text
postfix: () . ?
unary:   ! -
product: * /
sum:     + -
compare: == != < > <= >=
and:     &
or:      |
```

## 6. variant pattern

```glyph
+Command=Stop|Run(U)

>transition(system:System,command:Command):System
  command==Run(system.sequence)>>same_speed(system,command)
  command==Run(speed)>>new_speed(system,speed)
  command==Stop>>stop(system)
  _>>system
```

- `command==Stop`: unit variant照合
- `command==Run(_)`: payload無視
- `command==Run(speed)`: 新しい局所名へ束縛
- `command==Run(system.sequence)`: 既存式との値比較

## 7. 時相制約

### 宣言

```glyph
?name(parameters)=formula
```

### 演算子

```text
!P             否定
P & Q          論理積
P | Q          論理和
P >> Q         含意
@A P           Always
@E P           Eventually
@E 500ms P     bounded eventually
P U Q          strong until
P W Q          weak until
```

裸の`A`、`E`、`AE`、`EA`は受理しない。Unicodeの`□/◇`も受理しない。

単項演算子は、各演算子に`@`を付けて連結する。

```glyph
@A@E 1s heartbeat
@E@A stable
```

意味:

```text
@A@E 1s heartbeat = @A(@E 1s heartbeat)
@E@A stable       = @E(@A stable)
```

演算子と識別子の境界には空白または`(`が必要。

```text
@E@A stable    # 演算子列
@E@A(stable)   # 演算子列
@E@Astable     # エラー
EAstable       # 単一識別子
```

優先順位:

```text
1. ! @A @E @E duration
2. U W
3. &
4. |
5. >> 右結合
```

例:

```glyph
?ack(*Observation)=@A(send>>@E 500ms ack)
?safe(*Observation)=@A(!authorized>>closed)
?wait(*Observation)=closed W authorized
?live(*Observation)=@A@E 1s heartbeat
?conv(*Observation)=@E@A stable
```

### 有限トレース判定

```rust
pub enum TemporalVerdict {
    Satisfied,
    Violated,
    Pending,
}
```

- `@A P`: 途中で反例が出れば違反。終了まで反例がなければ満足
- `@E P`: P成立時に満足。終了まで成立しなければ違反
- `@E d P`: 期限内成立で満足。期限超過または未解決終了で違反
- `P U Q`: Q前のP違反、またはQ未到達終了で違反
- `P W Q`: Q未到達でも終了までPが成立すれば満足

## 8. 組込み関数

```text
Ok(x)
Err(e)
Some(x)
None
min(a,b)
max(a,b)
finite(x)
```

## 9. 文法概要

```text
program          := (macro | declaration | temporal-spec)*
macro            := "@" Name "=" expr
declaration      := product | sum | alias | function | extern
product          := "*" Name "(" compact-fields? ")"
sum              := "+" Name "=" variant ("|" variant)*
alias            := "=" Name "=" compact-type
function         := ">" signature ("=" expr | NEWLINE guard+)
extern           := "!" signature ("=" expr)?
signature        := Name "(" compact-params? ")" ":" compact-type
guard            := INDENT (expr | "_") ">>" expr
temporal-spec    := "?" Name "(" temporal-params? ")" "=" formula
formula          := implication
implication      := or-formula (">>" implication)?
or-formula       := and-formula ("|" and-formula)*
and-formula      := until-formula ("&" until-formula)*
until-formula    := unary-formula (("U" | "W") unary-formula)*
unary-formula    := "!" unary-formula
                  | "@A" unary-formula
                  | "@E" duration? unary-formula
                  | "(" formula ")"
                  | atom
```

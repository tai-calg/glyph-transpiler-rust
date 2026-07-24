# Glyph Type Algebra IR

## Purpose

Glyphの純粋な積型、直和型、型別名を、和と積からなる型代数へ射影する。

```text
Glyph product / sum declarations
        ↓
glyph.type-algebra-ir v1
        ├── semiring normal form
        ├── exact cardinality when decidable
        ├── impossible-type detection
        ├── type-isomorphism classes
        ├── bounded exhaustive values
        └── generated finite bijections and tests
```

この機能は新しい表面構文を追加しない。既存の`*Product`、`+Sum`、`=Alias`宣言だけを解析する。

## Algebra

型を次の対応で扱う。

| Glyph / type | Algebra |
|---|---|
| `Never` | `0` |
| `Unit`または`()` | `1` |
| `+Choice=A|B` | `A + B` |
| `*Pair(left:A,right:B)` | `A * B` |
| `Option<A>` / `O<A>` | `1 + A` |
| `Result<A,E>` / `R<A,E>` | `A + E` |

積は直和へ分配し、因子順を正規化する。したがって、次の二型は同じ標準形を持つ。

```glyph
+AorB=HasA(A)|HasB(B)
*Left(x:X,choice:AorB)

*XA(x:X,a:A)
*XB(x:X,b:B)
+Right=InA(XA)|InB(XB)
```

```text
Left  = X * (A + B) = A * X + B * X
Right = X * A + X * B = A * X + B * X
```

型名、variant名、フィールド名は標準形へ含めない。標準形が等しい宣言は、純粋な値集合として同型候補になる。

## Conservative boundary

次の対象は自動的に展開しない。

- 未知の外部型
- 再帰型の再帰参照
- `Vec`、ハンドル、デバイス型など任意の型コンストラクタ
- Capability、Resource、World、Protocol、Handler、Law

未知または再帰参照は記号的な原子として残す。このため、根拠のない有限性や同型を推測しない。

型同型はRustのメモリレイアウト、ABI、性能、フィールドの業務上の意味が同一であることを表さない。

## Cardinality and impossible types

標準形が定数だけで構成される場合、値数を十進文字列として正確に出力する。

```glyph
+Bit=Off|On
*Pair(left:Bit,right:Bit)
*Impossible(value:Never)
```

```text
|Bit|        = 2
|Pair|       = 2 * 2 = 4
|Impossible| = 4 * 0 = 0
```

値数が`0`の型は`impossible: true`になる。未知の原子を含む型は`cardinality_exact: false`になり、値数を出力しない。

## Exhaustive cases

既定上限は64値である。値を完全列挙でき、値数が上限以下の場合だけ`exhaustive_cases`を生成する。

対象は次の構成に限定する。

- `Never`
- `Unit` / `()`
- `bool`
- 上記だけから構成される積型・直和型・型別名
- 列挙可能な`Option`、`Result`、tuple

巨大な整数型、未知型、再帰型は列挙しない。有限性が判明しても上限を超える場合は列挙しない。

## Generated conversions

同じ標準形を持つ二型が、空でない有限型として完全列挙できる場合、双方向変換関数を`type-algebra.generated.rs`へ生成する。

```rust
pub fn glyph_convert_pair_to_quad(value: Pair) -> Quad
pub fn glyph_convert_quad_to_pair(value: Quad) -> Pair
```

変換は列挙順に基づく決定的な全単射である。variant名やフィールド名から意味対応を推測しない。例えば`Red`と`Error`のような名前が一致または不一致でも、業務上の意味が等しいとは判断しない。

生成ファイルには次も含む。

- 列挙値の重複がないことを確認するテスト
- 双方向変換が恒等写像へ戻ることを確認するround-tripテスト

利用例:

```rust
mod generated {
    include!("generated.rs");
}

mod type_algebra {
    include!("type-algebra.generated.rs");
}
```

## Artifacts

Glyph 0.4へ明示的にopt-inした入力では、通常のdiagram bundleへ次を追加する。

| File | Content |
|---|---|
| `type-algebra-ir.json` | 標準形、値数、不可能型、同型クラス、列挙値、変換可否 |
| `type-algebra.generated.rs` | 有限型の双方向変換関数と網羅・round-tripテスト |

旧構文だけの入力では追加ファイルを出力しない。既存のlegacy artifact集合を維持するためである。

## Schema

```json
{
  "schema": "glyph.type-algebra-ir",
  "version": 1,
  "source_name": "design.glyph",
  "exhaustive_limit": 64,
  "types": [],
  "isomorphism_classes": [],
  "conversions": []
}
```

既存のGlyph 0.4 Public IR schemaは変更しない。Type Algebra IRは独立した追加artifactである。

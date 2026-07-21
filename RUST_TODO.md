# 条件分岐とRust TODO契約

## 条件分岐

Glyphでは`if / else if / else`という予約語を増やさず、順序付きガードを条件式として使う。

```glyph
+Kind=Negative|Zero|Positive

>classify(x:I):Kind
  x<0 >> Negative
  x==0 >> Zero
  _ >> Positive
```

意味:

```text
if x < 0
else if x == 0
else
```

上から評価し、最初に成立した節の値を関数全体の値にする。最後の`_`は必須の`else`であり、到達不能な入力を残さない。

variant patternも同じガード列で書く。

```glyph
+C=Stop|Run(U)

>speed(c:C):U
  c==Stop >> 0
  c==Run(n) >> n
```

したがって、Glyphのアルゴリズム記述には次を使用できる。

- ガードによる`if / else if / else`
- variant guardによる`match`
- 直接・相互再帰
- ラムダ
- `/>`による処理連結
- 純粋関数値

## 複雑なアルゴリズムをRustへ残す

計算量、メモリ配置、SIMD、unsafe、専用ライブラリなどを含む処理は、Glyph内へ無理に記述しない。`~`で型付き契約だけを書く。

```glyph
*Graph(nodes:U,edges:U)
*Path(cost:U)

~shortest_path(graph:Graph,start:U,goal:U):Path # TODO: Dijkstra/A*をRustで設計

>plan(graph:Graph,start:U,goal:U):Path=
  shortest_path(graph,start,goal)
```

`~`の意味:

```text
純粋関数
型契約はGlyphに存在
アルゴリズム本体はRustに存在
Glyphの図とcall graphには残る
外部作用境界ではない
```

`>`、`~`、`!`の責任は異なる。

| 記号 | 意味 | 本体 |
|---|---|---|
| `>` | Glyphで記述する純粋関数 | Glyph |
| `~` | Rustで記述する純粋・不透明関数 | `manual.rs` |
| `!` | ファイル、通信、GPIO等の外部作用境界 | host側 |

## 生成Rust

Glyph:

```glyph
~optimize(path:Path):Path # TODO: O(n log n)以下を目標
>run(path:Path):Path=path /> optimize
```

生成ロジック:

```rust
pub fn run(path: Path) -> Path {
    crate::manual::optimize(path)
}
```

Studioは初回だけ`.glyph/<source>/manual.rs`を作る。

```rust
// Created once by Glyph Studio.
// This file is intentionally not overwritten after creation.
use crate::generated::*;

pub fn optimize(path: Path) -> Path {
    todo!("Glyph ~optimize: TODO: O(n log n)以下を目標")
}
```

`manual.rs`は利用者が所有するファイルであり、Glyphの保存・再コンパイルでは上書きしない。自動生成される`generated.rs`を直接編集してはならない。

## `/>`との接続

`~`関数は純粋関数としてパイプラインへ置ける。

```glyph
>plan(graph:Graph):Path=
  graph
  /> build_candidates
  /> choose_path
  /> optimize
```

ここで`optimize`だけを`~`にしても、前後の型検査とLogic図は維持される。

## 使用基準

Glyphで書く:

- 分岐の意味
- 状態遷移
- データの流れ
- 小さな変換
- 安全条件と時相条件
- アルゴリズムの入出力契約

`~`でRustへ残す:

- 計算量設計が主要課題になる処理
- 大規模探索、最適化、グラフアルゴリズム
- SIMD、GPU、unsafe、FFI
- 外部crate固有の詳細
- 500文字の設計スケッチを壊す長い実装

`~`は未設計部分を隠すためではなく、**設計上必要な契約をGlyphに残したまま、実装詳細だけを適切な言語へ降ろす境界**である。

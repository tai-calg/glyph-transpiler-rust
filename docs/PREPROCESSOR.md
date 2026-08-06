# Glyph raw preprocessor

Glyphの`@`には、役割の異なるマクロ構文と時相演算子がある。

| 構文 | 展開段階 | 用途 |
|---|---|---|
| `@NAME text` / `@NAME ... @end` | 全パーサーより前 | 任意のGlyphソース断片 |
| `@name(args) expression` | 式をASTへ変換した後 | 引数付きの式変換 |
| `@A` / `@E` | 時相制約式 | Always / Eventually |

マクロ定義では、名前と本体を空白で区切る。

```glyph
@MAX 100
@limit(x,high) min(x,high)
```

旧形式の`@NAME=text`と`@name(args)=expression`も移行互換として受理するが、新規コードでは使用しない。

rawマクロはCプリプロセッサと同じく裸の識別子で呼び出す。`${NAME}`や`@define`は使わない。

## 1行rawマクロ

```glyph
@MAX 100
@INPUT_TYPE SensorInput
@EDGE sensor -> ctl
@DECL *INPUT_TYPE(value:U)
```

使用:

```glyph
DECL

>cap(x:U):U
  x>MAX >> MAX
  _ >> x

system Controller
  entry ctl
  source sensor

EDGE
```

展開後:

```glyph
*SensorInput(value:U)

>cap(x:U):U
  x>100 >> 100
  _ >> x

system Controller
  entry ctl
  source sensor

sensor -> ctl
```

置換対象は完全な識別子トークンだけになる。

```glyph
@IN Value

IN       # Valueへ展開
Input    # 展開しない
MIN      # 展開しない
```

## 複数行rawマクロ

```glyph
@NORMALIZE
  positive :=
    x<0 >> -x
    _ >> x
  limited :=
    positive>MAX >> MAX
    _ >> positive
  limited
@end
```

使用:

```glyph
>normalize(x:I):I
  NORMALIZE
```

呼出し行のインデントを本体全行へ加算する。複数行マクロは行へ単独で置く。

不正:

```glyph
result := NORMALIZE
NORMALIZE /> encode
```

## ASTマクロ

ASTマクロは引数付きの式テンプレートになる。

```glyph
@MAX 100
@limit(x,high) min(x,high)

>run(x:U):U=limit(x,MAX)
```

呼出し側では通常の関数と同じ形で`limit(x,MAX)`と書く。引数は文字列ではなく構文木として置換するため、引数式の演算子構造を保持する。

基本規則:

1. `@name(parameter,...) expression`の形で定義する
2. 呼出しは`name(argument,...)`と書く
3. 引数個数は定義と一致させる
4. 展開後の式を通常どおり型検査する
5. 自己参照と相互参照による循環展開はエラーにする

## 名前規則

rawマクロ名は次の正規表現に一致しなければならない。

```text
[A-Z][A-Z0-9_]*
```

有効:

```text
MAX
INPUT_TYPE
LIMIT_2
```

無効:

```text
max
InputType
_INTERNAL
```

大文字を必須にし、関数引数、局所値、関数名との暗黙の衝突を減らす。

`A`と`E`は時相演算子`@A` / `@E`のため予約済みになる。rawマクロにもASTマクロにも使用できない。

```glyph
@A other       # エラー
@E(x) x        # エラー
```

ASTマクロは、それ以外の小文字名を使用できる。

```glyph
@MAX 100
@limit(x) min(x,MAX)
>run(x:U):U=limit(x)
```

rawプリプロセッサが先に`MAX`を展開し、その後ASTマクロ`limit`を解析する。

## 新旧構文の判定

旧構文は、最初の空白より前に`=`がある場合だけ認識する。

```glyph
@EDGE=sensor -> ctl   # 旧構文: EDGE / sensor -> ctl
@EXPR=x + y * z      # 旧構文: EXPR / x + y * z
```

新構文では最初の空白が名前と本体の境界になる。そのため、本体を`=`から始められる。

```glyph
@ALIAS =Count=U      # 新構文: ALIAS / =Count=U
```

## 文字列置換の意味

rawマクロは式マクロではなく、任意のソース断片を置換する。そのため括弧を自動追加しない。

```glyph
@NEXT x+1
>f(x:I):I=NEXT*2
```

展開後:

```glyph
>f(x:I):I=x+1*2
```

`(x+1)*2`が必要なら定義側に括弧を書く。

```glyph
@NEXT (x+1)
```

これはCのobject-like macroと同じ責任分担になる。

## コメント

`#`以降は展開しない。

```glyph
@MAX 100
>f():I=MAX # MAXは説明文として残る
```

展開後:

```glyph
>f():I=100 # MAXは説明文として残る
```

## 再帰展開

```glyph
@BASE 10
@LIMIT BASE+5
```

`LIMIT`は`10+5`へ展開される。循環は未使用であっても拒否する。

```glyph
@X Y
@Y X
```

```text
raw macro cycle: X -> Y -> X
```

展開深度、展開行数、展開文字数にも上限がある。

## コンパイル順序

```text
source
  ↓
raw macro collection and expansion
  ↓
system / compact syntax / AST macro extraction
  ↓
parse / type check / Rust / IR / diagrams
```

rawマクロは最初に動くため、次を含む任意のGlyph構文を生成できる。

- 型宣言
- 関数宣言
- `system`
- `machine`
- `:=`ブロック
- guard / variant match
- `/>` pipeline
- `~` Rust contract
- `!` effect boundary
- 時相制約

時相制約内でrawマクロを使う場合も、展開後の式には`@A` / `@E`を明示する。

```glyph
@LIMIT 500ms
?deadline(done:B)=@E LIMIT done
```

## Studioの保存と再構築

Glyph Studioでは、キー入力だけではプリプロセッサ、構文解析、型検査、IR生成、図のレイアウトを実行しない。入力はeditor bufferと`Unsaved`表示だけを更新する。

`Save & Render`または`Ctrl/Cmd + S`で次を順に実行する。

```text
editor source
  -> atomic file save
  -> IncrementalCompiler
  -> CompilationPipeline
  -> raw preprocessing
  -> parse / type check / IR generation
  -> I/O図・状態遷移図のrender
```

アプリ上でマクロを追加または変更して保存すると、その保存内容を再プリプロセスした結果からRust、IR、I/O図、状態遷移図を再生成する。

外部エディタによるファイル保存もwatcherが検出し、同じコンパイル経路を通る。ホットリロード専用の別プリプロセッサは持たない。

配信されるStudio HTMLには、Compileボタン、`/api/preview`呼出し、preview timer、`Ctrl/Cmd + Enter`によるコンパイル操作を含めない。

## Source map

複数行展開では、展開済み行番号と元ファイル行番号が一致しない。Glyphは各生成行について次を記録する。

```json
{
  "expanded_line": 12,
  "source_line": 30,
  "macro_stack": ["NORMALIZE", "LIMIT_BRANCH"],
  "definition_lines": [3, 10]
}
```

- `source_line`: 呼出し元の元ソース行
- `macro_stack`: 展開に参加したrawマクロ
- `definition_lines`: 各マクロの定義開始行

コンパイラ診断、Semantic model、Architecture、Algorithm IR、Execution IR、Mermaidリンクは`source_line`へ戻す。

## 生成物

Studioおよび`glyphc.py --diagram-dir`は次を追加生成する。

```text
preprocessed.glyph
preprocessor-map.json
```

`preprocessed.glyph`は問題調査用の完全な展開結果になる。設計の正本は元の`.glyph`ファイルになる。

## 制限

- rawマクロはトークン単位の文字列置換であり、型安全ではない
- ASTマクロは式だけを対象とする
- rawマクロは文字列リテラルを特別扱いしない
- 条件付き定義、可変長引数、ファイルincludeはない
- 複数行rawマクロは行へ単独で置く

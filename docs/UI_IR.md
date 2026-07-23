# Glyph UI IR and Generic Gradio Renderer

## 1. 目的

任意の純粋Glyph関数を、特定のアプリ名やfield名へ依存せず、人間が操作できるUIへ投影する。

```text
Glyph source
  ↓ IncrementalCompiler
validated CompilationModel
  ↓ UiIrBuilder
glyph.ui-ir version 1
  ↓ UI adapter
Gradio component tree
  ↓ LivePureGlyphRuntime
Versioned World execution
```

UI IRはGradio固有ではない。Gradioは最初のprojectionであり、将来はWeb Component、Tauri、CLI form等へ同じIRを投影できる。

## 2. 設計原則

1. Glyphの業務ロジックをUI Hostへ複製しない。
2. sourceをUI側で再parseしない。検証済み`CompilationModel`だけを使う。
3. 型から判断できない表示意図を勝手に推測しない。
4. UI IRはsemantic widget種別を持ち、Gradio component名を持たない。
5. `!`、`~`、未知型を暗黙のPython callbackへ接続しない。
6. UI component graphはActive Worldの型付きsignatureへ対応する。
7. function bodyだけのhot-swapではUIを再構築しない。
8. 型・signature変更はLive Imageのmigration規則へ従い、実行中UIへ無条件適用しない。

## 3. 起動

optional依存:

```bash
python3 -m pip install -r requirements-gradio.txt
```

自動選択:

```bash
python3 glyph_gradio.py examples/gradio_profile.glyph
```

関数を明示:

```bash
python3 glyph_gradio.py design.glyph --function calculate
```

UI IRだけを生成:

```bash
python3 glyph_gradio.py examples/gradio_motor.glyph \
  --check \
  --ui-ir-output build/motor-ui-ir.json
```

Gradioをimportせずに`--check`できるため、Compiler環境とUI環境を分離できる。

## 4. Entry functionの決定

次の順序で一つの純粋関数を選ぶ。

1. `--function`で明示された関数
2. `render`
3. `main`
4. 公開純粋関数が一つだけならその関数

候補が複数あり、上記で一意に決まらない場合はエラーにする。走査順から暗黙選択しない。

`__glyph_`で始まるcompiler helperは候補へ含めない。

## 5. Schema

```json
{
  "schema": "glyph.ui-ir",
  "version": 1,
  "source": "examples/gradio_profile.glyph",
  "title": "Render · Glyph App",
  "action": {
    "id": "action:render",
    "name": "render",
    "label": "Render",
    "source_line": 12,
    "inputs": [],
    "output": {}
  },
  "candidates": ["choose_access", "is_adult", "render"]
}
```

すべてのinput/output nodeは次を持つ。

```text
id
path
label
type
kind
role
required
```

必要に応じて次を持つ。

```text
default
minimum
maximum
choices
children
description
```

IDは表示順ではなく、roleとsemantic pathから生成する。

```text
input:profile.name
input:profile.age
output:return.access
```

## 6. 型からUI kindへの写像

### 6.1 入力

| Glyph type | UI IR kind | Gradio既定projection |
|---|---|---|
| `F`, `D`, float | `number` | Number |
| `U`, `I`, integer | `integer` | integer Number |
| `B`, `bool` | `checkbox` | Checkbox |
| `S`, `String` | `text` | Textbox |
| 積型 | `object` | Accordion内へfieldを再帰展開 |
| payloadなし直和型 | `select` | Dropdown |
| tuple | `json` input | JSON |
| `Result`, `Option` input | `json` | JSON |
| payloadあり直和型 | `json` | 明示variant JSON |
| 未知型・再帰型 | `json` | JSON |

### 6.2 出力

| Glyph type | UI IR kind | 表示 |
|---|---|---|
| number/integer | `metric` | metric card |
| bool | `status` | status badge |
| text | `text` | text card |
| 積型 | `object` | nested card grid |
| payloadなし直和型 | `badge` | variant badge |
| tuple | `tuple` | item cards |
| `Result` | `result` | success/error branch |
| `Option` | `option` | None/value |
| その他 | `json` | structured JSON |

型だけではSliderの意味範囲、単位、色、グラフ軸、主表示fieldを決定できない。そのためversion 1はNumber、Checkbox、Textbox、Dropdown、JSONという保守的な入力を生成する。

## 7. 入力再構築

Gradio componentはleaf field単位に生成される。event時にsemantic pathから元の関数引数を再構築する。

```text
input:profile.name   → profile.name
input:profile.age    → profile.age
input:profile.active → profile.active
```

結果:

```python
{
    "profile": {
        "name": "Ada",
        "age": 35,
        "active": True,
    }
}
```

このmappingを`LivePureGlyphRuntime.invoke("render", arguments)`へ渡し、Pure Runtime側でも積型field、primitive type、integer rangeを再検証する。

unit variantは`VariantValue(enum_name, variant)`へ変換する。payload variantは次のJSONを要求する。

```json
{
  "variant": "Run",
  "values": [80]
}
```

named-field variant:

```json
{
  "variant": "Fault",
  "fields": {
    "code": 12
  }
}
```

## 8. 汎用Gradio画面

生成画面は次を持つ。

```text
Hero
├─ app title
└─ entry function

Typed input form
├─ primitive controls
├─ nested product groups
└─ Run / Reset

Result
├─ structured result card
└─ raw JSON

Runtime
├─ Active World
├─ definition count
├─ Pending Patch
└─ compile diagnostic

History
├─ invocation
├─ World
├─ action
└─ result summary

Source / UI IR
├─ Active Glyph source
└─ generated glyph.ui-ir
```

`gr.State`はブラウザsessionの履歴だけを保持する。Glyph Worldと定義世代はprocess側の`LivePureGlyphRuntime`が所有する。

## 9. Hot reload

### 9.1 function body変更

signatureが同じ場合はLive Imageが新Worldをcommitする。component graphは同じまま、次の操作から新Worldの関数本体を実行する。

### 9.2 compile error

Source errorをRuntime領域へ表示し、最後の有効Worldを継続する。

### 9.3 type/signature変更

UI component graphは起動時のActive Worldから生成される。型またはsignature変更はmigration classでPendingとなる。汎用Gradio Hostは自動承認しない。

migrationを外部からcommitした場合、component graphは旧signatureのままなのでHost再起動が必要である。将来はUI IR差分とtransactional component-tree replacementを別段階で実装する。

## 10. 実証例

### 温度

```bash
python3 glyph_gradio.py examples/gradio_temperature.glyph
```

- nested product input
- float
- bool output
- unit sum output

### プロフィール

```bash
python3 glyph_gradio.py examples/gradio_profile.glyph
```

- text
- unsigned integer
- checkbox
- nested product
- access-level variant

### モーター

```bash
python3 glyph_gradio.py examples/gradio_motor.glyph
```

- multiple numeric fields
- boolean control
- clamp logic
- mode variant

三例は同じ`UiIrBuilder`と`build_gradio_app`を使用する。rendererに`TemperatureView`、`fahrenheit`、`ProfileInput`、`MotorInput`等の名前を埋め込まない。

## 11. 非目標

version 1では次を行わない。

- 自然言語field名から単位や範囲を推測する
- 数値を自動的にSliderへする
- 出力を自動的にchartへする
- `!` effect boundaryを任意Python関数へ接続する
- `~`を自動実行する
- variant-pattern guardをPure Runtimeで実行する
- migration後のGradio component graphを実行中に差し替える
- arbitrary HTML/JavaScriptをGlyphから注入する

## 12. 次段階

1. Glyph内の明示的UI hint Contract
2. unit、range、step、placeholder、secret等のmetadata
3. table、line、bar、image、audio等のoutput projection
4. multiple action tabs
5. UI IR差分とtransactional component-tree reload
6. `!` Host Invocationとフォーム送信の統合
7. Law violation、Protocol trace、Resource stateのruntime visualization

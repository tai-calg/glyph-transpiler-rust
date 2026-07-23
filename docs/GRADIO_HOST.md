# Glyph Gradio Live Host

## 1. 目的

Glyphで記述した純粋ロジックを、Pythonへ式を複製せずGradioから実行し、人間向けの視覚的なアプリとして表示する。

```text
Glyph source
  ↓ IncrementalCompiler
validated CompilationModel
  ↓ PureGlyphProgram
immutable executable AST
  ↓ LivePureGlyphRuntime
Versioned World / Definition Cell dispatch
  ↓ Gradio Host
input / presentation / history / status
```

Gradioは温度変換式、温度帯の閾値、Resource規則を再実装しない。UI固有の日本語ラベル、カード配置、色、ゲージ、履歴だけを担当する。

## 2. 実行例

依存関係:

```bash
python3 -m pip install -r requirements-gradio.txt
```

起動:

```bash
python3 examples/gradio_temperature_app.py
```

任意のsource、host、port:

```bash
python3 examples/gradio_temperature_app.py \
  --source examples/gradio_temperature.glyph \
  --host 127.0.0.1 \
  --port 7860
```

## 3. 現在のGlyph構文上の注意

現在のトップレベル型宣言は行指向である。積型と直和型の宣言は、一つの物理行で閉じる。

有効:

```glyph
*TemperatureInput(celsius:F)
*TemperatureView(celsius:F,fahrenheit:F,kelvin:F,count:U,valid:B,band:TemperatureBand)
+TemperatureBand=Invalid|Freezing|Cold|Comfortable|Warm|Hot
```

現在は無効:

```glyph
*TemperatureView(
  celsius:F,
  fahrenheit:F
)
```

最初の行だけがparserへ渡るため、`')' が閉じられていない`となる。Gradio例はこの制約を受入試験で固定し、未対応の複数行型宣言を例示しない。

関数本体のordered guardは複数行で記述できる。

```glyph
>classify(celsius:F):TemperatureBand
  !is_valid(celsius) >> Invalid
  celsius<=0.0 >> Freezing
  celsius<18.0 >> Cold
  celsius<27.0 >> Comfortable
  celsius<35.0 >> Warm
  _ >> Hot
```

## 4. PureGlyphProgram

`glyph/pure_runtime.py`の`PureGlyphProgram`は、検証済み`CompilationModel.program`を直接実行する。source文字列を再parseしない。

対応:

- primitive number / bool / text input
- 積型の構築、field参照、Host mappingとの相互変換
- unit、tuple
- 直和型のunit / tuple / named-field variant
- 名前付き純粋関数呼出し
- ordered boolean guard
- `+ - * /`
- 比較、boolean `! | &`
- `min` / `max` / `finite`
- `Ok` / `Err` / `Some` / `None`
- `?`によるResult伝播
- alias解決
- integer range検査
- call-depth上限

意図的に拒否:

- `!` effect boundary
- `~` manual Rust implementation
- 動的function valueの実行
- variant-pattern guard
- native/JIT/Wasm code
- arbitrary Python callback

未対応構文をPython的に推測して実行しない。`PureRuntimeError`として境界で停止する。

## 5. Runtime value

積型はimmutableな`ProductValue`として保持する。

```text
ProductValue(
  type_name = TemperatureView,
  fields = (
    (celsius, 22.0),
    (fahrenheit, 71.6),
    ...
  )
)
```

Gradio境界では`glyph_to_python`によりdictへ変換する。Gradioから積型引数を渡す場合もdictを受け取り、fieldの欠落、余剰、型、整数範囲を検査する。

直和型は`VariantValue`で保持し、UI境界では次へ変換する。

```json
{
  "type": "TemperatureBand",
  "variant": "Comfortable"
}
```

## 6. LivePureGlyphRuntime

`LivePureGlyphRuntime`は次を所有する。

```text
IncrementalCompiler
CompiledLiveImage
source digest → PureGlyphProgram
file watcher
last compile diagnostic
```

実行時:

```text
invoke(render)
  ↓ optional file refresh
WorldLeaseを取得
  ↓
leaseされたWorldのsource digestを解決
  ↓
対応するPureGlyphProgramを実行
  ↓
InvocationResult(world_version, value)
```

Worldの取得後にsourceが更新されても、そのinvocationはleaseした旧Worldのprogramを使い続ける。

### 6.1 function body変更

型付きsignatureが同じ場合は`hot-swap`である。

```text
World 1で実行中のrequest → World 1を継続
新規request                → World 2を使用
```

### 6.2 compile error

file watcherはdiagnosticを保持し、Active Worldを変更しない。Gradio画面にはsource errorを表示するが、変換操作は最後に成功したWorldで継続できる。

### 6.3 migration / reader blocker

型、Resource、Reader変更は既存Live Image規則に従ってPending Patchとなる。Gradio温度例は自動的に危険なpatchを承認しない。

## 7. Gradio画面

画面は次の領域を持つ。

```text
Hero
├─ Glyph × Gradioの責務説明
│
Input panel
├─ temperature slider
├─ presets
├─ invoke
└─ history reset
│
Result card
├─ Fahrenheitの主表示
├─ Celsius / Fahrenheit / Kelvin
├─ TemperatureBand
├─ thermometer gauge
└─ invocation / World
│
Live Image status
├─ Active World
├─ definition count
├─ Pending Patch
└─ compile diagnostic
│
History LinePlot
└─ Celsius / Fahrenheit
│
Glyph source
└─ watcherが読んでいる現在のsource
```

`gr.State`はブラウザsessionごとの履歴だけを保持する。Glyph Worldはprocess側runtimeが所有する。`gr.Timer`はLive Image状態とsource表示を定期更新する。

## 8. Gradio version boundary

例はGradio 6系へ固定する。

```text
gradio>=6.0,<7
pandas>=2.0,<3
```

Gradio 6ではapp-levelのthemeとCSSを`Blocks.launch()`へ渡す。CSSは主に`elem_id`、`elem_classes`、自前`gr.HTML`内のclassを対象とし、Gradio内部DOMの非公開構造へ過度に依存しない。

## 9. ファイル構成

```text
examples/gradio_temperature.glyph
    唯一の変換・分類ロジック

glyph/pure_runtime.py
    validated AST interpreterとLive World dispatch

examples/gradio_temperature_app.py
    Gradio Hostとpresentation

requirements-gradio.txt
    optional UI dependencies

tests/test_pure_runtime.py
    runtime semantics / hot reload / last-good World

tests/test_gradio_host_example.py
    source構文 / Python構文 / formula非重複 / dependency boundary
```

## 10. 次の拡張

- variant-pattern guardのruntime評価
- `~`をHost登録済みpure callableへ接続
- `!`をHost Invocation IRへlowerして明示adapterへ接続
- typed migration functionの実行
- GradioからPending Patchを監査・commitする管理画面
- Protocol / Law runtime traceの可視化
- PureGlyphProgramをinterpreter code-handle実装としてDefinition Cell一般interfaceへ統合

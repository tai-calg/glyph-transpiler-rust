# Glyph I/O and State Diagram App

## Purpose

`python3 glyph.py <file.glyph>`は、一つのGlyph sourceから次の二つのcompiler-derived viewを表示する。

1. Checked System Context / I/O topology
2. State transitions

アプリケーションは設計対象を実行しない。PythonやJavaScript側でGlyphの業務ロジックを再実装せず、検証済みIRだけを表示する。

```text
Glyph source
  -> CompilationModel
  -> checked ArchitectureIR
  -> ExecutionStructureIR
  -> normalized StateMachine analysis
  -> glyph.io-state-views v2
  -> browser renderer
```

## Start

```bash
python3 glyph.py examples/acceptance/motor_safety.glyph
```

既定では`127.0.0.1`へbindしてブラウザを開く。portを固定する場合:

```bash
GLYPH_DIAGRAM_PORT=7860 python3 glyph.py design.glyph
```

ブラウザの自動起動を止める場合:

```bash
GLYPH_DIAGRAM_NO_BROWSER=1 python3 glyph.py design.glyph
```

## Checked System Context view

正規の`system` declarationは、entry、typed port、主要なデータ・戻り値・作用flowを宣言する。

```glyph
system MotorSafety
  entry control

  in state:MotorState
  in sensor:Input
  out receipt:Receipt

  state -> control
  sensor -> control
  control -> receipt
  control -> write_motor
```

`system MotorSafety=control`は廃止されている。

### System Flowとcall graph

System Flowとcall graphは同一ではない。

```text
code call: control -> sensor
data flow: sensor -> control
```

明示`system`がある場合、I/O viewはSystem Contextを表示する。内部の`decide`や`step`をentry call graphから自動的に境界へ混入させない。

```text
state  --data--> control --returns--> receipt
sensor --data--> control
control --effect--> write_motor
```

call graphが必要な場合は別viewとして扱う。`system`宣言がないsourceに限り、whole-program call graphをfallback I/O viewとして表示する。

### Explicit external boundaries

外部装置、入力provider、外部serviceはtyped `ext` signatureで宣言する。

```glyph
ext sensor():Input
ext panel():PanelInput
ext database(query:Query):Record|DatabaseError
```

`ext`はoutside → systemの極性を持つ。未宣言名をrendererがexternal componentとして補うことはない。

```glyph
system Broken
  entry control
  in sensor:Input
  out result:Input
  sensor -> control
  control -> result

>control():Input=sensor()  # sensorが未宣言なのでコンパイルエラー
```

修正:

```glyph
system Fixed
  entry control
  in sensor:Input
  out result:Input
  sensor -> control
  control -> result

ext sensor():Input
>control():Input=sensor()
```

`ext`と`!`はHostへ接続されるが、Architecture上の意味は異なる。

| declaration | polarity | role |
|---|---|---|
| `ext sensor():Input` | outside → system | external input / provider |
| `!write_motor(command:Command):Receipt` | system → outside | effect boundary |
| `~layout(input:Input):Layout` | system → manual Rust dependency | logically pure implementation contract |

### Checked flow evidence

System edgeはarrowを生成する命令ではない。Architecture assertionであり、コンパイラがtyped code evidenceを付与できる場合だけ受理する。

| edge kind | browser label | evidence |
|---|---|---|
| input data | `data` | entry parameterまたはexternal input read |
| successful return | `returns` | return typeとentryからの到達性 |
| external effect | `effect` | effect boundaryへの到達path |
| internal/manual responsibility | `flow` | declared call path |

次はコンパイルエラーになる。

- undeclared entry
- undeclared endpoint
- codeに存在しないflow edge
- port型とfunction型の不一致
- `ext`と`!`の極性逆転
- reachable external boundaryのsystem記載漏れ

Glyph短縮型`U/B/F/I`と、正規化後の`u16/bool/f32/i16`は同じcanonical typeとして比較する。

### Internal declarations

明示systemに接続されていないhelperや別entryは、`Internal and unconnected declarations`へ分離する。これは未宣言という意味ではなく、選択中のpublic System Contextに含めていないという意味である。

完全な意味論は[`CODE_DERIVED_SYSTEMS.md`](CODE_DERIVED_SYSTEMS.md)を参照する。ファイル名は既存link互換のため維持している。

## State-transition view

状態遷移図は、検証済み`machine` declarationからだけ生成する。

```glyph
machine Motor(state:MotorState,input:Input)
  select=state.mode
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted
```

描画前に、compiler-derived transition relationを正規化する。

1. selector variantから完全なstate集合を得る
2. wildcard source `*`をconcrete stateへ展開する
3. wildcard target `*`をself-transitionへ解決する
4. ordered guardで到達不能なbranchを除く
5. initial stateからreachabilityを計算する
6. compiler helperのsource locationを元Glyph lineへ戻す

ブラウザは`Any state`を実stateとして描画しない。

表示内容:

- initial-state marker
- selectorの全variant
- success / failure annotation
- concrete state-to-state transition
- transition condition
- unreachable stateのdashed outline
- source line link付きstatic diagnostic

主な診断:

- `unreachable-branch`
- `unreachable-state`
- `state-independent-transition`
- `no-static-transitions`

`:=` blockはcompiler helperへloweringされるが、state analysisはconstructorを追跡し、UIには元のGlyph source locationだけを示す。

`machine`がない場合、state machineを名前や型から推測しない。

## Live editing

- editはdebounce付きcompile previewを開始する
- `Compile`は保存せず即時previewする
- `Save`はsourceを書き込み、再compileする
- external file changeをwatchする
- compile error時も最後のvalid diagramを保持する
- node、transition label、diagnosticからsource lineへ移動できる

## Output artifact

compile成功時:

```text
.glyph/<source-stem>/io-state-views.json
```

Schema:

```text
schema: glyph.io-state-views
version: 2
```

JSON modelには次を含む。

- checked systems
- typed ports
- semantic edges and evidence
- external/effect/manual boundary classification
- fallback call graph
- type declarations
- normalized machines
- concrete states and transitions
- reachability and diagnostics

## Non-goals

- runtime invocation
- effect execution
- scheduler / thread / process placement
- business-semantic inference
- `machine`なしのstate-machine inference
- undeclared external component inference
- call edgeをphysical wireまたはSystem Contextとみなすこと

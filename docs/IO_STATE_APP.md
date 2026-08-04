# Glyph I/O and State Diagram App

## Purpose

`python3 glyph.py <file.glyph>`は、一つのGlyph sourceから次の二つのcompiler-derived viewを表示する。

1. Executable System boundary / function-call topology
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

## Executable System boundary view

正規の`system` declarationは、値や型や矢印を再宣言せず、外部境界となる関数だけを指定する。

```glyph
system MotorSafety
  entry control
  source sensor
  sink write_motor
```

各役割は呼出しの主導方向で決まる。

| item | declaration kind | meaning |
|---|---|---|
| `entry control` | `>control(...)` | outsideがSystem内部関数をinvokeする |
| `source sensor` | `ext sensor(...)` | Systemが外部関数を呼び、値をpullする |
| `sink write_motor` | `!write_motor(...)` | Systemが外部関数を呼び、作用を要求する |

関数の引数型、正常戻り型、失敗型は各関数宣言から取得する。

```glyph
ext sensor():Input|SensorError
!write_motor(command:Command):Receipt|MotorError

>control(state:MotorState):Receipt|ControlError
  input := sensor()?
  command := decide(state,input)
  write_motor(command)
```

`Receipt|ControlError`の失敗側をSystem境界から落としてはならない。entryの完全な関数シグネチャがSystemのrequest/response契約になる。

`system MotorSafety=control`、`in`、`out`、System内の`a -> b`は正規記法ではない。

### Function calls only

System図のノードは関数だけ、矢印は実コードから導出した関数呼出しだけに限定する。

```text
[ENTRY] control(state: MotorState) -> Receipt | ControlError
    calls -> [SOURCE] sensor() -> Input | SensorError
    calls -> [INTERNAL] decide(state, input) -> Command
    calls -> [SINK] write_motor(command) -> Receipt | MotorError
```

`Input`、`MotorState`、`Receipt`などの値や型を独立ノードとして関数と同列に置かない。型は関数ノードの引数・戻り値欄に表示する。

entryから到達する通常関数と`~`関数は`INTERNAL`として自動収集する。Systemブロックへ列挙しない。

```glyph
~optimize(input:Input):Plan
>decide(input:Input):Plan=optimize(input)
```

`~optimize`はHost側で実装する純粋関数であり、外部作用ではないため`sink`にしない。

### Explicit external boundaries

外部装置、入力provider、外部serviceはtyped `ext` signatureで宣言する。

```glyph
ext sensor():Input
ext panel():PanelInput
ext database(query:Query):Record|DatabaseError
```

正しいSystem宣言:

```glyph
system Fixed
  entry control
  source sensor

ext sensor():Input
>control():Input=sensor()
```

未宣言の外部呼出しはコンパイルエラーになる。

```glyph
system Broken
  entry control

>control():Input=sensor()
```

`ext`、`!`、`~`はHostへ接続されるが、System上の意味は異なる。

| declaration | call direction | System role |
|---|---|---|
| `ext sensor():Input` | system -> outside -> value | `source` |
| `!write_motor(command:Command):Receipt` | system -> outside effect | `sink` |
| `~layout(input:Input):Layout` | system -> manual pure Rust | `internal` |

### Completeness checks

コンパイラはentryから実行可能なcall graphを辿り、System宣言と照合する。

次はコンパイルエラーになる。

- entryが未宣言、または`>`関数ではない
- sourceが未宣言、または`ext`関数ではない
- sinkが未宣言、または`!`関数ではない
- 宣言したsource/sinkへentryから到達できない
- entryから到達するsource/sinkの宣言漏れ
- 同じ関数を複数の境界役割へ割り当てる
- 未宣言関数への呼出し

Glyph短縮型`U/B/F/I`と、正規化後の`u16/bool/f32/i32`は同じcanonical typeとして扱う。

### Internal and unconnected declarations

entryから到達する内部関数はSystem図へ含める。entryから到達しない別entry候補や無関係なhelperは、`Internal and unconnected declarations`へ分離する。

完全な意味論は[`CODE_DERIVED_SYSTEMS.md`](CODE_DERIVED_SYSTEMS.md)を参照する。

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

## Editing and rebuild

- キー入力はeditor bufferと`Unsaved`表示だけを更新する
- キー入力ごとのpreprocess、compile、IR生成、graph layout、renderは行わない
- `Save & Render`または`Ctrl/Cmd + S`でsourceを書き込み、その後にpreprocessとcompileを実行する
- external file saveはwatcherが検出し、同じcompile pipelineで再構築する
- compile error時も保存自体は成立し、最後のvalid diagramを保持できる
- node、transition label、diagnosticからsource lineへ移動できる

保存時の処理順序:

```text
editor source
  -> atomic file save
  -> raw macro preprocessing
  -> parse / type check
  -> IR and diagram generation
  -> browser render
```

アプリが配信するHTMLには、Compileボタン、`/api/preview`呼出し、preview timer、`Ctrl/Cmd + Enter`によるcompile shortcutを含めない。

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

- checked Systems
- entry/source/sink/internal function classification
- complete function signatures
- derived call edges and evidence
- fallback whole-program call graph
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
- call edgeをphysical wireとみなすこと

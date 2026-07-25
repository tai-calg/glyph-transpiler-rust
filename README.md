# Glyph Rust

Glyphは、ソフトウェアの**構造・判断・状態・作用・時間制約・アルゴリズム骨格**を短いコードで記述し、同じ設計からRust、Mermaid、型付きIR、Glyph Studioを生成するDSLです。

詳細アルゴリズムをすべてGlyphへ移すのではなく、人間とAIが確認すべき設計をGlyphへ残します。計算量、複雑なデータ構造、unsafe、GPU処理などは`~`でRustへ委譲します。

```text
要求・自然言語
      ↓
Glyph design contract
├── Architecture
├── Data / Decision
├── State / Time
├── Algorithm skeleton
├── Capability / Resource
├── World / Protocol / Handler / Law
├── Raw preprocessor
└── Rust / Effect boundary
      ↓
Rust・Mermaid・versioned JSON IR
```

## 起動

### ファイルを指定せず起動

```bash
python3 glyph.py
```

カレントディレクトリの`.glyph/workspace.glyph`を開きます。初回だけドア制御のサンプルGlyphを自動作成し、ブラウザのエディタへ表示します。

`.glyph/workspace.glyph`が既に存在する場合は上書きしません。画面上の`Save`で保存した内容は次回起動時にも維持されます。

### 既存のGlyphファイルを開く

```bash
python3 glyph.py examples/acceptance/motor_safety.glyph
```

従来どおり任意の`.glyph`ファイルを指定できます。

Glyph Studioは次を一つの画面で扱います。

- Source editorと自動診断
- I/O topologyと状態遷移図
- Architecture / State / Logic / Flow / Time
- 生成Rust、host adapter、`manual.rs`
- Typed AST、Symbol、versioned IR
- 生成artifact一覧

### 状態遷移図の編集と出力

- 状態ノードとI/Oノードをドラッグして配置変更
- 通常ドラッグは8pxグリッドへ吸着
- `Shift`を押しながらドラッグすると1px単位で移動
- ノード選択後、矢印キーで微調整
- `Auto layout`で自動配置へ戻す
- `White`と会社提出向け`Monochrome`テーマを切替
- 表示中の図だけをSVG、2倍解像度PNG、横向きPDFへ出力

配置はブラウザの`localStorage`へ保存され、Glyphソース自体とは分離されています。詳細は[`docs/DIAGRAM_EDITOR.md`](docs/DIAGRAM_EDITOR.md)を参照してください。

CLI:

```bash
python3 glyphc.py design.glyph --check
python3 glyphc.py design.glyph \
  -o build/generated.rs \
  --host-output build/host.generated.rs \
  --diagram-dir build/diagrams \
  --ast-json build/typed-ast.json
```

## Glyph 0.4

Glyph 0.4は、現在のPlain構文を維持したまま、必要な値と処理だけへCapability、Resource、World、Protocol、Handler、Lawを付加します。

```glyph
'@WorkerRequest = Worker * App/Request
'>Exchange = -> Input >> <- Output
'!Policy = 'std.timeout(2s) >> 'std.return_error
'WorkerCall = {'WorkerRequest,'Exchange,'Policy}

resource Buffer[Ready|Done]

!process(
  buffer:own Buffer[Ready]
):own Buffer[Done]
  @{'WorkerCall}
```

Contract名は`'Name`、適用は`@{'Name}`で通常の型・値名と区別します。Protocol方向は`-> T`／`<- T`です。

完全な仕様、保証範囲、Host責任、コード例は[`docs/CONTRACTS.md`](docs/CONTRACTS.md)を参照してください。全層を接続した受入例は[`examples/acceptance/glyph04_system.glyph`](examples/acceptance/glyph04_system.glyph)です。

## 検証付きSystem Context

`system`はcall graphを生成する入口指定ではなく、**外部境界、typed port、主要なデータ・戻り値・作用flowを先に示すArchitecture contract**です。

```glyph
system MotorSafety
  entry cycle

  in state:MotorState
  in input:Input
  out receipt:Receipt

  state -> cycle
  input -> cycle
  cycle -> receipt
  cycle -> write_motor
```

`entry`は後ろに宣言した本体付き`>`関数へforward bindingできます。`system MotorSafety=cycle`は廃止されています。

```glyph
>normalize(raw:F):F=min(raw,1.0)

>decide(input:Input):Command
  input.emergency|input.fault >> Stop
  !input.enabled >> Stop
  _ >> Drive(normalize(input.raw))

>step(state:MotorState,input:Input):MotorState
  command := decide(input)
  next :=
    command==Stop >> MotorState(Stopped,Stop)
    command==Drive(speed) >> MotorState(Running,Drive(speed))
    _ >> MotorState(Faulted,Stop)
  next

!write_motor(command:Command):Receipt
>cycle(state:MotorState,input:Input):Receipt=write_motor(step(state,input).command)
```

System Flowとcall graphは別物です。

```text
System Context: input -> cycle -> receipt / write_motor
Call graph:     cycle -> step -> decide -> normalize
```

明示`system`のI/O図には公開境界だけを表示し、内部helperを自動混入させません。各edgeは次のtyped code evidenceを必要とします。

| flow | label | compiler evidence |
|---|---|---|
| caller input → entry | `data` | entry parameter名と型 |
| `ext` input → function | `data` | external readへの到達pathと成功型 |
| function → output | `returns` | 正常戻り型とentryからの到達性 |
| function → `!` | `effect` | effect boundaryへの到達path |
| function → function / `~` | `flow` | declared call path |

### `ext`: 明示的な外部入力境界

センサー、パネル、外部serviceなど、システム外部が所有するproviderは`ext`で宣言します。

```glyph
ext sensor():Input
ext database(query:Query):Record|DatabaseError
```

`ext`はoutside → system、`!`はsystem → outsideの極性を持ちます。未宣言名をdiagramだけでexternalへ補うことはありません。

```glyph
system Door
  entry control
  in sensor:Input
  out receipt:Receipt
  sensor -> control
  control -> receipt
  control -> lock

ext sensor():Input
!lock(state:DoorState):Receipt
>control():Receipt=lock(step(sensor()))
```

| declaration | role |
|---|---|
| `ext read_sensor():Input` | external input / provider |
| `!write_motor(command:Command):Receipt` | external effect |
| `~layout(input:Input):Layout` | logically pure manual Rust dependency |

一回の実行順序は通常の`>`関数で表します。新しい`runtime`宣言子は追加しません。永続状態だけを`machine`へ置きます。

詳細は[`docs/CODE_DERIVED_SYSTEMS.md`](docs/CODE_DERIVED_SYSTEMS.md)と[`docs/IO_STATE_APP.md`](docs/IO_STATE_APP.md)を参照してください。

## `@`: rawマクロと時相sigil

`@`は構文位置によって意味が決まります。

| 記法 | 意味 |
|---|---|
| `@NAME=text` | 1行rawマクロ |
| `@NAME ... @end` | 複数行rawマクロ |
| `@name(args)=expr` | AST式マクロ |
| `@A` | Always |
| `@E` | Eventually |
| `@{'Name}` | Glyph 0.4 Contract適用 |

### rawマクロ

```glyph
@MAX=100
@TYPE=SensorInput
@CONTROL=write_motor(step(state,sensor()).command)
```

使用側には裸の識別子を書きます。

```glyph
*TYPE(value:U)
>control(state:State):Receipt=CONTROL
```

置換は完全な識別子トークン単位です。`IN`を定義しても`Input`や`MIN`の一部分は置換しません。

複数行:

```glyph
@NORMALIZE
  normalized :=
    input.raw
    /> |x| min(x,MAX)
@end

>run(input:Input):F
  NORMALIZE
  normalized
```

rawマクロ名は`[A-Z][A-Z0-9_]*`に限定します。`A`と`E`は時相演算子のため予約済みです。

```glyph
@A=other   # エラー
@E(x)=x    # エラー
```

rawマクロはCと同じ文字列置換であり、括弧を自動追加しません。

```glyph
@NEXT=x+1
>f(x:I):I=NEXT*2  # x+1*2
```

詳細: [`docs/PREPROCESSOR.md`](docs/PREPROCESSOR.md)

## 型

```glyph
*Input(value:U,valid:B)
+Command=Stop|Run(U)|Fault(Error)
=Output=U|Error
```

短縮型:

```text
F  f32
D  f64
U  u16
I  i32
B  bool
T|E  Result<T,E>
```

積型のfield rowは関数引数へ展開できます。

```glyph
*S(v,t:F,r:U)
>decode(*S):S|Error
```

## 純粋関数とガード

単一式:

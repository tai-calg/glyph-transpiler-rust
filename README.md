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

## コードに基づく`system`ヘッダ

`system`は自由記述の構成図ではありません。**本体を持つ入口関数を指定し、その関数から実際に到達する呼出しだけをコンパイラがI/O図へ投影します。**

```glyph
system MotorSafety=cycle

machine Motor(state:MotorState,input:Input)
  select=state.mode
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted

# 以降に型・関数・作用境界を宣言する
```

`cycle`は後ろに宣言して構いません。ファイル全体を解析してからforward bindingします。

```glyph
>decide(input:Input):Command
  ...

>step(state:MotorState,input:Input):MotorState
  command := decide(input)
  ...

!write_motor(command:Command):Receipt

>cycle(state:MotorState,input:Input):Receipt=write_motor(step(state,input).command)
```

このコードからI/O図は次を導出します。

```text
cycle -> write_motor
cycle -> step
step  -> decide
```

コードに存在しないnodeや接続を`system`だけで作ることはできません。

### `ext`: 明示的な外部境界

センサー、パネル、外部サービスなど、Glyph外部から値を受け取るcomponentは`ext`で宣言します。

```glyph
ext sensor():Input
ext panel():PanelInput
```

`ext`は型付きHost境界です。未宣言の名前をsystem内に書いても自動的にexternalにはなりません。

```glyph
system Door=control
>control():Input=sensor()  # sensorが未宣言ならコンパイルエラー
```

修正:

```glyph
system Door=control
ext sensor():Input
>control():Input=sensor()
```

`ext`と`!`はどちらもHostへ接続されますが、設計上の役割を区別します。

| 宣言 | 意味 |
|---|---|
| `ext read_sensor():Input` | 外部component・外部入力契約 |
| `!write_motor(command:Command):Receipt` | 明示的な作用境界 |
| `~layout(input:Input):Layout` | Rust実装へ委譲する純粋契約 |

### 接続行は検証用assertion

必要なら、systemヘッダの下に期待する直接呼出しを書けます。

```glyph
system Door=control
  control -> sensor
  control -> step
```

これは矢印を追加する命令ではありません。コンパイラが実コードから同じ直接呼出しを導出できなければエラーになります。新規コードでは通常、`system Name=entry`だけで十分です。

詳細は[`docs/CODE_DERIVED_SYSTEMS.md`](docs/CODE_DERIVED_SYSTEMS.md)を参照してください。

## 全体例

```glyph
system MotorSafety=control

machine Motor(state:MotorState,input:Input)
  select=state.mode
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted

@MAX=100
@STOP_LIMIT=100ms

*Input(raw:F,enabled,emergency,fault,stopped:B)
+Command=Stop|Drive(F)
+Mode=Stopped|Running|Faulted
*MotorState(mode:Mode,command:Command)
*Receipt(command:Command)

?emergency_stop(*Input)=@A(emergency >> @E STOP_LIMIT stopped)
?fault_stop(*Input)=@A(fault >> @E STOP_LIMIT stopped)

ext sensor():Input

>decide(input:Input):Command
  normalized :=
    input.raw
    /> |x| min(x,1.0)

  command :=
    input.emergency|input.fault >> Stop
    !input.enabled >> Stop
    _ >> Drive(normalized)

  command

>step(state:MotorState,input:Input):MotorState
  command := decide(input)
  next :=
    command==Stop >> MotorState(Stopped,Stop)
    command==Drive(speed) >> MotorState(Running,Drive(speed))
    _ >> MotorState(Faulted,Stop)
  next

!write_motor(command:Command):Receipt
>control(state:MotorState):Receipt=write_motor(step(state,sensor()).command)
```

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
system Demo=control
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

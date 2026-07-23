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

```bash
python3 glyph.py examples/acceptance/motor_safety.glyph
```

Glyph Studioは次を一つの画面で扱います。

- Source editorと自動診断
- Architecture / State / Logic / Flow / Time
- 生成Rust、host adapter、`manual.rs`
- Typed AST、Symbol、versioned IR
- 生成artifact一覧

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

## ファイル先頭の設計ヘッダ

`system`と`machine`は、宣言本体を包むブロックではなく、ファイル全体の設計を先に示すヘッダです。正規形では、ファイル先頭に`system`、続けて`machine`を書き、その後に型・純粋関数・作用境界を記述します。

```glyph
system MotorSafety
  sensor -> decide
  decide -> step
  step -> write_motor

machine Motor(state:MotorState,input:Input)
  select=state.mode
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted

# 以降に型・関数・作用境界を宣言する
```

component、状態型、`next`関数はファイル全体を解析した後に名前解決するため、ヘッダから後続宣言へのforward bindingが可能です。既存sourceとの互換性のため末尾配置も受理しますが、README・examples・新規コードは先頭配置へ統一します。

## 全体例

```glyph
system MotorSafety
  sensor -> decide
  decide -> step
  step -> write_motor

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
@EDGE=sensor -> ctl
```

使用側には裸の識別子を書きます。

```glyph
system Demo
  EDGE

*TYPE(value:U)
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

```glyph
>double(x:U):U=x*2
```

ordered guard:

```glyph
+Kind=Negative|Zero|Positive

>classify(x:I):Kind
  x<0 >> Negative
  x==0 >> Zero
  _ >> Positive
```

上から最初に成立した枝を返します。最後の`_`は必須です。

variant pattern:

```glyph
+Command=Stop|Run(U)|Fault(Error)

>speed(command:Command):U
  command==Stop >> 0
  command==Run(n) >> n
  command==Fault(_) >> 0
  _ >> 0
```

## `:=`: 不変の中間値

`:=`は可変代入ではなく、一度だけ定義する不変値です。

```glyph
>normalize(x:I):I
  positive :=
    x<0 >> -x
    _ >> x

  limited :=
    positive>100 >> 100
    _ >> positive

  limited
```

同名再定義と引数shadowingはコンパイルエラーです。

## `/>`: pipelineとラムダ

```glyph
normalized :=
  value
  /> validate?
  /> |x| min(x,MAX)
  /> encode
```

```text
value /> f /> g = g(f(value))
```

pipeline lambdaは現在、1引数・単一式・non-capturing・pureに限定しています。

- 一度しか使わない短い変換: lambda
- 分岐の合流点、再利用する値、意味のある節目: `:=`

## `?`: Result伝播と時相制約

式末尾の`?`はResult失敗伝播です。

```glyph
>checked(x:U):U|Error
  value := validate(x)?
  Ok(value)
```

トップレベル行頭の`?name(...)=formula`は時相制約です。

```glyph
?always_safe(*Input)=@A !unsafe
?deadline(*Input)=@A(request >> @E 500ms response)
?heartbeat(*Input)=@A@E 1s heartbeat
?converges(*Input)=@E@A stable
?hold(*Input)=closed U authorized
?weak_hold(*Input)=closed W authorized
```

時相演算子:

| 記法 | 意味 |
|---|---|
| `@A P` | 常にP |
| `@E P` | いつかP |
| `@E 500ms P` | 500ms以内にP |
| `@A@E P` | 常に、再びPへ到達する |
| `@E@A P` | いつか、それ以降は常にP |
| `P U Q` | strong until |
| `P W Q` | weak until |

裸の`A`、`E`、`AE`、`EA`は受理しません。Unicodeの`□`、`◇`も受理しません。各Always/Eventually演算子に必ず`@`を付けます。

詳細: [`docs/TEMPORAL.md`](docs/TEMPORAL.md)

## `system`: Architecture

```glyph
system Door
  sensor -> authenticate
  authenticate -> decide
  decide -> lock
  decide -> alarm
```

componentは同名宣言へbindingされます。

| 宣言 | Architecture上の種類 |
|---|---|
| `>name` | Glyph pure function |
| `~name` | Rust pure implementation |
| `!name` | effect boundary |
| 型名 | data |
| 未定義名 | external component |

## `machine`: 状態機械

```glyph
machine Motor(state:MotorState,input:Input)
  select=state.mode
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted
```

状態遷移は純粋関数としてGlyphへ書き、時計、周期実行、I/O、違反後の復旧はhost側へ残します。

## `~`: Rust実装の純粋境界

```glyph
*Graph(nodes:U,edges:U)
*Path(cost:U)

~shortest_path(graph:Graph,start:U,goal:U):Path

>plan(graph:Graph,start:U,goal:U):Path
  path := shortest_path(graph,start,goal)
  path
```

`~`は型、call graph、Architecture上の位置だけをGlyphに残し、実装を`manual.rs`へ委譲します。Studioは`manual.rs`を初回だけ作成し、その後は上書きしません。

## `!`: 外部作用境界

```glyph
!read_sensor():Input
!write_motor(command:Command):Receipt
```

通信、GPIO、ファイル、DB、デバイスI/Oなどは`!`でhost adapterへ分離します。

## Source-level Logic IR

`:=`、分岐、pipeline、lambda、`~`、`!`、`?`から、lowering前のAlgorithm IRを生成します。

```text
algorithm-ir.json
logic.mmd
```

人間向けLogicには`__glyph_*`内部helperを表示しません。lowering後のcall graphは別の`execution-ir.json` / `execution.mmd`へ保存します。

## 生成物

```text
.glyph/<source-stem>/
├── preprocessed.glyph
├── preprocessor-map.json
├── architecture.mmd
├── architecture-ir.json
├── logic.mmd
├── algorithm-ir.json
├── execution.mmd
├── execution-ir.json
├── machine-<name>.mmd
├── temporal.mmd
├── source-map.json
├── index.md
├── typed-ast.json
├── generated.rs
├── host.generated.rs
├── manual.rs
├── capability-ir.json             # Glyph 0.4使用時
├── resource-flow-ir.json          # Glyph 0.4 resource使用時
├── contracts-ir.json              # Contract使用時
├── runtime-contract-ir.json       # 意味付きContract使用時
└── verification-report.json       # Glyph 0.4使用時
```

公開JSONには`schema`と整数`version`があります。

## Acceptance examples

```bash
python3 glyphc.py examples/acceptance/door_controller.glyph --check
python3 glyphc.py examples/acceptance/job_scheduler.glyph --check
python3 glyphc.py examples/acceptance/motor_safety.glyph --check
python3 glyphc.py examples/acceptance/glyph04_system.glyph --check
python3 -m unittest discover -s tests -p 'test_acceptance_*.py' -v
```

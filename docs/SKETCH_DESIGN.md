# Glyph ソフトウェアスケッチ設計

## 1. 目的

Glyphを、詳細実装前の短い記述から次を同時に確認できるソフトウェア設計DSLにする。

1. **Architecture** — どの実装済み処理がどの処理・境界を呼ぶか
2. **State** — どこから始まり、どう遷移し、どこが正常・異常状態か
3. **Logic** — どの条件で何を選ぶか
4. **Time** — 常に守る条件、期限内に成立すべき条件は何か

通常利用:

```bash
python3 glyph.py door.glyph
```

Studio内で、編集、保存、検査、Rust生成、図更新を同一プロセスで行う。

## 2. 設計原則

### 2.1 図とコードを二重記述しない

Architectureは自由記述の矢印ではなく、入口関数から到達する実call graphである。

```glyph
system Door=control
```

```glyph
ext sensor():Input
>decide(input:Input):Command=...
!write_lock(command:Command):Receipt
>control():Receipt=write_lock(decide(sensor()))
```

導出結果:

```text
control -> write_lock
control -> decide
control -> sensor
```

この対応により、図だけに存在する`decide`や、実際には呼ばれない`lock`を作れない。

### 2.2 外部componentは`ext`で明示する

```glyph
ext sensor():Input
ext panel():PanelInput
```

未宣言名はexternalとして補完せず、コンパイルエラーにする。

```text
undeclared name
  -> error
  -> declare with ext, !, ~, or >
```

### 2.3 境界の役割を分離する

```text
>    Glyph本体を持つ関数
ext  外部component・入力・service契約
!    設計対象が起こす作用境界
~    Rustへ委譲する純粋実装契約
```

すべてを同じ「外部箱」として扱わない。

### 2.4 局所ロジックだけを短縮する

- 図の主要ノードになる処理: 名前付き関数
- 一度しか使わない局所変換: `/>` lambda
- 外部component: `ext`
- 外部作用: `!`
- 再利用する判断: 名前付き関数またはAST macro

コンパイラが生成するlambda・`:=` helperはArchitectureでflattenし、公開componentにしない。

## 3. 目標例

```glyph
system Door=control

machine Door(state:State,input:Input)
  select=state.mode
  init=State(Closed)
  next=step(state,input)
  success=Open
  failure=Alarm

*PanelInput(open_request:B,authorized:B)
*SensorInput(obstruction:B)
*Input(open_request:B,authorized:B,obstruction:B)
+Mode=Closed|Opening|Open|Closing|Alarm
*State(mode:Mode)
*Receipt(state:State)

ext panel():PanelInput
ext sensor():SensorInput

>combine(p:PanelInput,s:SensorInput):Input=
  Input(p.open_request,p.authorized,s.obstruction)

>step(state:State,input:Input):State
  state.mode==Closed&input.open_request&input.authorized >> State(Opening)
  state.mode==Opening&input.obstruction >> State(Alarm)
  state.mode==Opening >> State(Open)
  _ >> state

!write_door(state:State):Receipt

>control(state:State):Receipt=
  write_door(step(state,combine(panel(),sensor())))

?safe(*Input)=@A(!authorized >> !open_request)
```

同じsourceから生成するもの:

```text
Architecture  controlから到達する宣言済みcall
State         Closed/Opening/Open/Closing/Alarm
Logic         guard優先順、combine、step
Time          未認可時のopen_request禁止
Rust          型、関数、Host adapter、monitor
```

## 4. `system`宣言

### 4.1 文法

```ebnf
system_decl      = "system" IDENT "=" IDENT NEWLINE system_assertion* ;
system_assertion = INDENT IDENT "->" IDENT NEWLINE ;
```

正規形:

```glyph
system Door=control
```

`control`はファイル後方に宣言してよい。完全なProgramを構築後に名前解決する。

### 4.2 意味

1. entryが本体を持つ`>`関数であることを確認する。
2. entryからnamed callを辿る。
3. 呼出し先をsymbol tableで解決する。
4. compiler helperをflattenする。
5. resolved componentとcall edgeからArchitectureIRを構築する。

```text
Architecture edge = declared call dependency
```

これは「毎回実行される」「並列である」「物理wireである」ことまでは意味しない。

### 4.3 optional assertion

```glyph
system Door=control
  control -> sensor
  control -> step
```

接続を追加する記法ではなく、コードに同じdirect callがあることを検査するassertionである。

### 4.4 静的検査

- system名の重複
- entry未宣言
- entryが`ext`/`!`など本体なし境界
- reachable call未宣言
- assertion node未宣言
- assertion edgeがコードに存在しない
- assertion重複
- self-edge assertion

## 5. `ext`宣言

```ebnf
external_decl = "ext" IDENT "(" parameters? ")" ":" type NEWLINE ;
```

```glyph
ext camera(frame:FrameRequest):Frame|CameraError
```

`ext`はHost実装を要求する型付き契約であり、Glyph本体を持たない。I/O図では`external`として宣言済みportを表示する。

## 6. Architecture IR

```text
ArchitectureIR
└── systems: ArchitectureSystem[]

ArchitectureSystem
├── id
├── name
├── entry
├── components: ArchitectureComponent[]
└── edges: ArchitectureEdge[]

ArchitectureComponent
├── local_id
├── name
├── kind: function | external | effect | rust
├── binding
└── source

ArchitectureEdge
├── from
├── to
└── call-site source
```

Architecture componentは必ずsymbolへbindingされる。unresolved/conceptual componentは存在しない。

## 7. Studioの4ビュー

### Architecture

entryから導出したcall graph、component種別、型付きportを表示する。

### State

`machine`からinitial、transition、success、failure、reachabilityを表示する。

### Logic

名前付き関数のguard treeとpipelineを表示する。

### Time

`?`制約をtrigger、obligation、deadline、finish semanticsへ正規化する。

## 8. ラムダとpipeline

```glyph
>run(x:U):U=
  x
  /> inc
  /> |n| n+1
  /> clamp
```

`/>`はleft-associativeで、lambdaは単項・非capture・純粋である。Architectureではsynthetic lambda nodeを公開せず、その内部から到達するuser declarationだけをentry graphへ反映する。

## 9. 完成条件

- I/O図の全nodeが宣言済みsymbolへ対応する
- I/O図の全edgeが実call siteへ対応する
- `ext`の型がportへ表示される
- 未宣言名はエラーになる
- systemとmachineが同一sourceの実装を参照する
- Rust、IR、図が決定的に生成される
- browser testで架空node・`undeclared` portが存在しないことを確認する

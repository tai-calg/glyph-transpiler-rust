# Glyph execution structure

## Scope

R3-1〜R3-4は、Glyphの実行構造をコードと同じASTから生成し、次を即座に確認できるようにする。

- どの純粋関数と作用境界が接続されているか
- どのガード条件からどの結果へ進むか
- machineの初期状態、遷移先、正常終端、異常終端
- どの時相制約がどの観測列を監視するか
- 図の要素が元ソースの何行目に対応するか

図は実行意味を推測する別パーサーから作らず、コンパイルに使うProgram AST、時相AST、machine ASTから生成する。

## R3-1: ExecutionStructureIR

```text
ExecutionStructureIR
├── source_name
├── nodes: ExecutionNode[]
├── edges: ExecutionEdge[]
├── machines: MachineView[]
└── temporal: TemporalView[]
```

すべての要素は`SourceRef(line,column)`を持つ。

### Dataflow

```text
ExecutionNode
- id
- kind: function | effect | decision | branch | result | error
- label
- source

ExecutionEdge
- source_id
- target_id
- kind: call | control | return | error
- label
- source
```

ガード関数はdecision nodeへ変換する。ネストした関数呼出しは呼出し順のedgeへ変換し、`?`による伝播には`Ok`と`Err`のedgeを付ける。

### Machine

```text
MachineView
- state_type
- selector
- initial_state
- next_function
- success_state
- failure_state
- states
- transitions
```

遷移元がガード条件から特定できない場合、IRは推測せず`*`（Any state）とする。例えば`command==Stop`だけでは現在のmodeを限定しないため、`Any state -> Stopping`として表示する。

### Temporal

```text
TemporalView
- name
- formula
- reference_monitor
- streaming_monitor
- source
```

## R3-2: machine declaration

```glyph
machine Controller(state:System,input:Input)
  select=state.mode
  init=System(Idle,0,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted
```

### Header

第1引数を状態、残りを1周期の入力とする。状態型は積型でなければならない。

### Properties

| Property | Requirement |
|---|---|
| `select` | `state.field`。fieldの型は直和型 |
| `init` | 状態積型のコンストラクタ |
| `next` | 名前付き純粋関数呼出し。状態型または`Result<State,E>`を返す |
| `success` | selector型に存在する正常終端variant |
| `failure` | selector型に存在する異常終端variant |

5項目はすべて必須で、重複、未知のproperty、存在しないvariant、誤った状態型、誤ったnext戻り値を静的に拒否する。

machine宣言はRust itemを生成しない。実行構造IRと設計図のための宣言である。

## R3-3: Mermaid output

```bash
python3 glyphc.py examples/system_controller.glyph \
  --diagram-dir build/system-controller
```

出力:

```text
build/system-controller/
├── execution.mmd
├── machine-controller.mmd
├── temporal.mmd
├── execution-ir.json
├── source-map.json
└── index.md
```

- `execution.mmd`: 関数、ガード、作用境界、Result経路
- `machine-<name>.mmd`: 初期状態、状態遷移、正常・異常終端
- `temporal.mmd`: 観測列から各モニタへの接続
- `index.md`: 全図と仕様要約を一つにまとめたMarkdown
- `execution-ir.json`: エディタや別レンダラーが利用できる完全IR

## R3-4: source cross-reference

Mermaid flowchart nodeには次のclick directiveを生成する。

```text
click fn_step "../examples/system_controller.glyph#L48" "Open source line 48"
```

図から元`.glyph`行へ移動できる。

逆方向は`source-map.json`で提供する。

```json
{
  "source": "examples/system_controller.glyph",
  "line_to_views": {
    "48": [
      {
        "kind": "execution-node",
        "id": "fn_step",
        "diagram": "execution.mmd"
      }
    ]
  }
}
```

`index.md`にも同じ逆引き表を生成する。将来のVS Code拡張はこのJSONを使い、Glyph行のCodeLensから対応図を開ける。

## Guard arrow spacing

ガード区切り`>>`の前後の空白は任意。

```glyph
input.v<LOW>>Stop
input.v<LOW >> Stop
```

両方を同じASTへ変換する。標準の記述例とドキュメントでは視認性の高い空白付き形式を使う。

## Deliberate limitations

- 状態遷移のtargetは状態積型コンストラクタから抽出する
- 遷移元がselector比較として現れない場合は`Any state`になる
- helper関数は状態型を返す名前付き純粋関数に限り再帰的に追跡する
- 動的callee、作用境界による状態生成、任意の計算から導出されるvariantは推測しない
- Mermaidは表示形式であり、ExecutionStructureIRが意味上の正本である

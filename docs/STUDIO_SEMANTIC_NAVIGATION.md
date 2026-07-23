# Glyph Studio Semantic Navigation

## 1. Purpose

Glyph Studioの七つの直交ビューを、単なる独立したJSON表示ではなく、同一設計を意味単位で探索できる環境へ統合する。

```text
CapabilityでBufferを選択
    ↓
Resource identity rho:process:buffer
    ↓
processのstate transition
    ↓
WorkerRequest World
    ↓
RetryPolicy / verification / Host requirement
```

この統合はブラウザでGlyph sourceを再解析して実現しない。Compilerが検証済みのtyped designをStudio専用Semantic Indexへ投影し、UIはそのIndexを選択・表示するだけである。

## 2. Architecture

```text
Glyph source
    ↓
CompilationPipeline
    ↓
validated typed design
    ↓
studio_views.build_studio_views
    ├─ seven orthogonal view projections
    └─ studio_semantics.build_semantic_index
           ├─ canonical entities
           └─ typed relations
    ↓
glyph.studio-views version 2
    ├─ views
    └─ semantic_index
    ↓
Studio selection state
    ├─ cross-highlight
    ├─ Inspector
    ├─ history
    ├─ deep link
    └─ command palette
```

依存方向は一方向である。

```text
typed design
    → presentation projection
    → semantic index
    → browser selection
```

禁止事項:

- UIがGlyph sourceをparseする
- UIが型、Resource identity、Contract適用を推測する
- 表示順や配列indexだけからentity identityを作る
- Studio Semantic IndexをCompiler Public IRへ混入する
- Protocol choice/parallelを存在しない線形edgeへ変換する

## 3. Schema boundary

Studio ViewModel:

```text
schema: glyph.studio-views
version: 2
```

Semantic Index:

```text
schema: glyph.studio-semantic-index
version: 1
```

`glyph.studio-semantic-index`はStudio専用schemaである。次のCompiler Public IRを変更しない。

- `glyph.capability-ir`
- `glyph.resource-flow-ir`
- `glyph.contracts`
- `glyph.runtime-contract-ir`
- `glyph.verification-report`
- `glyph.host-requirements`

## 4. Canonical entity IDs

IDは表示順に依存しない。

| Entity | ID example |
|---|---|
| Function/effect/opaque boundary | `function:process` |
| Resource declaration | `resource:Buffer` |
| Aggregate | `aggregate:ProcessError` |
| Plain type | `type:Input` |
| Function place | `place:process:param:buffer` |
| Symbolic Resource identity | `identity:rho:process:buffer` |
| Resource transition | `resource-transition:rho:process:buffer:process:75:transition` |
| World | `world:WorkerRequest` |
| Protocol | `protocol:NormalizeExchange` |
| Protocol event | `protocol-event:NormalizeExchange:root.0` |
| Handler | `handler:RetryPolicy` |
| Handler node | `handler-node:RetryPolicy:step:0` |
| Law | `law:ObservationSafe` |
| Host requirement | `host-requirement:handler:fetch:RetryPolicy:0` |
| Verification item | content-derived digest ID |

### 4.1 Declaration-kind normalization

Glyphの実宣言kindは次を含む。

```text
function
effect
opaque
product
sum
alias
resource
```

Studio entityは意味軸へ正規化する。

```text
function / effect / opaque
    → function:<name>

product / sum
    → aggregate:<name>

alias
    → type:<name>
```

これにより、`!process`へWorld Contractを適用しても、Capability viewの`function:process`とWorld viewの対象が別entityへ分裂しない。

### 4.2 Resource identity

Resourceは型名とinstance identityを分離する。

```text
resource:Buffer
identity:rho:process:buffer
```

同型Resourceが複数あっても、`rho`を統合しない。

### 4.3 Protocol event

Protocol event IDはflatten後の通し番号ではなく、Protocol ASTのstructured pathを使う。

```text
protocol-event:Structured:root.0.0
protocol-event:Structured:root.1.0
```

choiceとparallelのevent間に、意味上存在しない`next` relationを生成しない。

### 4.4 Verification

Verification itemはstatement、subject、axis、classes、lineのcanonical JSONからdigestを生成する。配列の並べ替えでIDが変化しない。

未知subjectは削除せず、次のsynthetic entityとして保持する。

```text
subject:runtime:external clock
```

## 5. Relation taxonomy

Semantic Index version 1で使用するrelation:

```text
declares
accepts
returns
stores
owns
shares
links
borrows
mutably-borrows
converts
moves
creates
preserves
transitions
instance-of
applies
executes-in
uses-protocol
handled-by
constrained-by
contains
sends
receives
next
requires-host
verified-by
```

relationは必ず、存在するentity同士を接続する。未定義endpointや未知relation kindはIndex構築時にエラーとする。

### 5.1 Direction examples

```text
function:process
    transitions
identity:rho:process:buffer
```

```text
function:normalize
    uses-protocol
protocol:NormalizeExchange
```

```text
world:WorkerRequest
    applies
function:process
```

```text
function:process
    executes-in
world:WorkerRequest
```

```text
handler:RetryPolicy
    requires-host
host-requirement:handler:fetch:RetryPolicy:0
```

## 6. Selection model

ブラウザが保持する選択状態は一つだけである。

```text
selected_entity_id: string | null
```

選択操作:

- card/node/row click: entityを選択
- source line button: sourceへ移動
- entity double click: 選択した上でsourceへ移動
- Escape: 選択解除

この分離により、「関連を調べたい」と「コードへ移動したい」が同じclickで競合しない。

## 7. Cross-highlight

選択時の表示:

```text
selected entity
    強調

directly related entities
    relation強調

unrelated semantic entities
    dimmed
```

Cross-highlightは現在表示中のviewにあるDOMだけへ適用する。別viewの意味対象はInspectorの`Open in`から移動できる。

## 8. Inspector

Inspectorは選択entityについて次を表示する。

- kind
- label
- canonical ID
- source line
- available views
- details
- incoming/outgoing typed relations

relation itemを選ぶと、関連entityへ選択を移す。

## 9. Selection history

選択履歴はブラウザ内で管理する。

```text
Alt + Left
    previous selection

Alt + Right
    next selection

Escape
    clear selection
```

履歴はCompiler stateではなく、一時的なUI stateである。

## 10. Deep links

URL queryにactive viewとselectionを保存する。

```text
/?view=Resource&select=identity:rho:process:buffer
```

ページを開いた時点でentityが存在すれば選択を復元する。存在しないIDは無視し、Compiler modelを変更しない。

## 11. Command palette

`Ctrl/Cmd + K`で全Semantic Indexを検索する。

検索対象:

- canonical ID
- kind
- label
- aliases
- details

選択結果にsource lineと対応viewがあれば、適切なviewを開きsourceへ移動する。

現在のview内filterは別機能として維持する。

## 12. Error and preview behavior

Compile error時は、従来どおり最後に成功したSemantic Indexを保持する。

```text
editing source + current diagnostic
    alongside
last valid semantic graph
```

Previewはsource fileを保存せず、新しい有効snapshotが生成できた場合だけSemantic Indexを更新する。

## 13. Acceptance conditions

- entity IDが重複しない
- 全relation endpointが存在する
- relation kindがschema集合に含まれる
- effect/opaque Contract targetがfunction entityへ統合される
- aggregate memberが表示indexから`type:0`等を生成しない
- Resource identityが`rho`単位で保持される
- Protocol pathが安定し、choice/parallelへ偽の線形edgeを作らない
- Verificationの未知subjectを保持する
- 同じtyped designから決定的なIndexを生成する
- Public IRを変更しない
- plain sourceでは空Indexを生成する
- Inspector、history、deep link、command paletteが存在する
- JavaScriptが`node --check`を通る
- stabilization、legacy compatibility、Rust tests、Clippyが成功する

## 14. Non-goals

今回のSemantic Navigationには含めない。

- Compiler Public IRへのglobal graph追加
- graph layout engine
- multi-hop path query UI
- diagramからsourceを編集するround trip
- runtime traceとstatic graphの統合
- live collaboration
- project-wide multi-file symbol navigation
- concrete Host runtimeのsimulation

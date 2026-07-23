# Glyph Studio 0.4 Orthogonal Views

## 1. Purpose

Glyph Studioは、一つのGlyph設計を単一の巨大な図へ押し込まず、同じcanonical design modelから複数の直交ビューとして表示する。

実装するビューは次の七つである。

1. Capability view
2. Resource identity/state view
3. World/Region view
4. Protocol sequence view
5. Handler exit graph
6. Law/monitor view
7. Verification-strength view

各ビューは別の設計軸を強調するが、別々にGlyph sourceを解析したり、独自の意味論を導出したりしない。各ビューはStudio Semantic Indexを介して同じ意味対象へ接続される。

## 2. Canonical data flow

```text
Glyph source
    ↓
CompilationPipeline
    ↓
typed design JSON
    ├─ capabilities
    ├─ resource_flow
    ├─ runtime_contracts
    ├─ verification
    └─ host_requirements
    ↓
studio_views.build_studio_views
    ├─ seven orthogonal views
    └─ studio_semantics.build_semantic_index
    ↓
glyph.studio-views version 2
    ├─ views
    └─ semantic_index
    ↓
Studio HTTP state / studio-views.json / browser UI
```

`build_studio_views`はsource parserではない。検証済みtyped designを表示用に並べ替え、stable semantic IDを付けるprojectionである。

`build_semantic_index`もsource parserではない。ViewModelとtyped designに既に存在するidentity、Contract適用、型、Host requirement、verificationをclosed entity/relation graphへ構成する。

次を禁止する。

- Studio UIでGlyph sourceを再解析すること
- Studio専用にResource identityやContract rowを再導出すること
- Public IRと異なるCapability、World、Protocol、Handler、Law意味論を持つこと
- Viewごとに別のcompile pipelineを走らせること
- 表示順や配列indexをcanonical type IDとして使用すること
- UIでrelationを推測すること

## 3. Snapshot boundary

`StudioSnapshot`は従来の`semantic`と`execution_ir`に加えて`glyph04_views`を保持する。

```text
StudioSnapshot
    source
    diagnostics
    artifacts
    semantic
    execution_ir
    glyph04_views
        views
        semantic_index
```

正常build時には`studio-views.json`も`.glyph/<source-name>/`へ出力する。

compile error時は、sourceとdiagnosticを更新し、最後に成功したartifacts、semantic model、execution IR、Glyph 0.4 views、Semantic Indexを保持する。これにより、壊れた編集中sourceと直前の有効設計を同時に確認できる。

`manual.rs`の所有権境界は変更しない。基底`GlyphStudio`は`manual.rs`を書き込まず、`GlyphProjectStudio`だけが初回scaffold作成と以後のユーザー所有を管理する。

## 4. View definitions

### 4.1 Capability view

Source:

- `capabilities.resources`
- `capabilities.functions`
- `capabilities.aggregates`
- `capabilities.operations`

表示内容:

- Resource型と許可state
- function parameter/resultのCapability型
- aggregateへ保存されるCapability
- move、borrow、capability conversion

このビューはRustの`Rc`、`Arc`、`Weak`等を表示しない。それらはHost実装の選択であり、Glyph Capability意味論ではない。

function、effect、opaqueの宣言は、Studio意味空間では`function:<name>`へ統合する。Glyph表面記号の違いによって、同じ作用境界が別entityへ分裂してはならない。

### 4.2 Resource identity/state view

Source:

- `resource_flow.transitions`

表示内容:

- symbolic resource identity (`rho:*`)
- Resource型
- Capability種別
- state列
- identityをpreserve/create/transitionするfunction

同型Resourceを型名だけで統合しない。表示単位はsymbolic identityである。

aggregate memberやfunction型はViewModelが保持するcanonical `type_entity_id`を使用する。表示用indexから`type:0`や`resource:1`等を生成してはならない。

### 4.3 World/Region view

Source:

- `runtime_contracts.worlds`
- `runtime_contracts.applications[*].row.world`

表示内容:

- World Contract
- execution locus
- dynamic Region path
- Contractが適用されるfunction/type/field

WorldとRegionをthread、executor、process、deviceへ固定しない。

### 4.4 Protocol sequence view

Source:

- `runtime_contracts.protocols[*].root`
- `runtime_contracts.applications[*].row.protocol`

表示内容:

- send / receive event
- message type
- structured Protocol path
- sequence、choice、parallel、repeat等の親control
- Protocol適用target

イベントを表示用の線形配列へ変換する場合も、元のcontrol pathを保持する。choiceやparallelを消失させてはならず、存在しない`next` relationを生成してはならない。

### 4.5 Handler exit graph

Source:

- `runtime_contracts.handlers`
- Handlerに対応する`host_requirements.operations`
- `runtime_contracts.applications[*].row.handler`

表示内容:

- target exit
- timeout、retry、rollback、compensate、fallback、return_error等の宣言順
- stepごとのverification class
- semantic Host requirement
- Handler適用target

現段階のgraphは宣言されたfailure handling chainを表示する。具体scheduler、timer、transaction engineの実行graphは生成しない。

### 4.6 Law/monitor view

Source:

- `runtime_contracts.laws`
- Lawに対応する`host_requirements.operations`
- `runtime_contracts.applications[*].row.laws`

表示内容:

- canonical formula
- verification class
- monitor delivery requirement
- Law適用target

既存temporal monitorへlowerできるLawと、Host runtime obligationとして残るLawを同じ画面から確認できる。

### 4.7 Verification-strength view

Source:

- `verification.summary`
- `verification.items`

表示内容:

- static / model / runtime / trusted別の件数
- semantic axis × verification class matrix
- 個別obligation
- source line

強度は単一の順位ではなく、保証主体の直交分類として表示する。

未知subjectは削除せずsynthetic subject entityとしてSemantic Indexへ保持する。

## 5. Semantic navigation

七つのview要素はstable `entity_id`を持つ。選択状態は一つのcanonical entity IDで表現する。

```text
selected_entity_id: string | null
```

UI動作:

- card/node/row click: semantic entity選択
- source line button: editorの該当行へ移動
- entity double click: 選択してsourceへ移動
- selected entity: 強調
- directly related entity: relation強調
- unrelated semantic entity: dimmed
- Inspector: details、available views、incoming/outgoing relation
- Alt+Left / Alt+Right: 選択履歴
- Escape: 選択解除
- `?view=...&select=...`: deep link
- Ctrl/Cmd+K: global semantic Command Palette

意味ID、relation taxonomy、履歴、deep linkの詳細は`STUDIO_SEMANTIC_NAVIGATION.md`に記載する。

## 6. General UI behavior

- 七つのGlyph 0.4 viewはDesign navigation groupへ配置する。
- Architecture、State、Logic、Flow、Time、Rust、Host、AST等の従来viewは維持する。
- 現在view内のfilterと、全Semantic Indexを検索するCommand Paletteを分離する。
- 0.4を使用しないsourceでは七つのviewとSemantic Indexは空状態を表示し、legacy compile結果を変更しない。
- Overviewには0.4のResource、identity、World、Protocol、Handler、Law、semantic entity、relation数を追加する。
- Previewはsource fileを保存せず、同じViewModel/Index pipelineを使用する。
- editor幅、theme、active view等はbrowser-local presentation stateとして保持する。

一般的な編集・Preview・appearance設計は`STUDIO_UX.md`に記載する。

## 7. Artifacts and API

Studio HTTP `/api/state`は次を含む。

```json
{
  "glyph04_views": {
    "schema": "glyph.studio-views",
    "version": 2,
    "enabled": true,
    "summary": {},
    "views": {},
    "semantic_index": {
      "schema": "glyph.studio-semantic-index",
      "version": 1,
      "entities": [],
      "relations": []
    }
  }
}
```

Studio専用ViewModelであり、Glyph 0.4 Public IR schemaには追加しない。Public IRを置換せず、UI向けprojectionとして扱う。

## 8. Non-goals

現在の実装には含めない。

- diagramからGlyph sourceを書き換えるround-trip editing
- concrete Host runtimeの実行・simulation
- runtime eventのlive streaming
- multi-hop semantic path-query UI
- 大規模設計向けlayout engine
- Protocolのmessage timing simulation
- Law違反traceのinteractive replay
- project-wide multi-file semantic navigation

## 9. Acceptance conditions

- 同じtyped designから七つのviewとSemantic Indexを一回だけ構築する。
- plain sourceでは0.4 viewを無効化し、空Indexを生成する。
- complete 0.4 exampleで七つ全てのview dataが生成される。
- entity IDが一意である。
- 全relation endpointが存在する。
- relation kindが固定taxonomyに含まれる。
- effect/opaque targetがfunction entityへ統合される。
- aggregate memberはcanonical type IDを使用する。
- Protocol eventはdirection、type、structured pathを保持する。
- choice/parallel間に偽の線形relationを作らない。
- Resource viewはsymbolic identity単位でstateを表示する。
- unknown verification subjectを保持する。
- compile error時に最後の有効viewとIndexを失わない。
- `manual.rs`を上書きしない。
- package root API、Public IR schema、legacy生成物を変更しない。
- JavaScriptが`node --check`を通る。
- Python tests、stabilization、main compatibility、Rust tests、Clippyが成功する。

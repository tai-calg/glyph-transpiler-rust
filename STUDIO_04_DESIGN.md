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

各ビューは別の設計軸を強調するが、別々にGlyph sourceを解析したり、独自の意味論を導出したりしない。

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
    ↓
glyph.studio-views version 1
    ↓
Studio HTTP state / studio-views.json / browser UI
```

`build_studio_views`はsource parserではない。検証済みtyped designを表示用に並べ替えるprojectionである。

次を禁止する。

- Studio UIでGlyph sourceを再解析すること
- Studio専用にResource identityやContract rowを再導出すること
- Public IRと異なるCapability、World、Protocol、Handler、Law意味論を持つこと
- Viewごとに別のcompile pipelineを走らせること

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
```

正常build時には`studio-views.json`も`.glyph/<source-name>/`へ出力する。

compile error時は、sourceとdiagnosticを更新し、最後に成功したartifacts、semantic model、execution IR、Glyph 0.4 viewsを保持する。これにより、壊れた編集中sourceと直前の有効設計を同時に確認できる。

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

イベントを単純な線形配列へ変換する場合も、元のcontrol pathを保持する。choiceやparallelを消失させてはならない。

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

## 5. UI behavior

- 七つのGlyph 0.4 viewは既存Studio tabへ追加する。
- Architecture、State、Logic、Flow、Time、Rust、Host、AST等の従来viewは維持する。
- source lineを持つcard、node、rowを選択するとeditorの該当行へ移動する。
- 0.4を使用しないsourceでは七つのviewは空状態を表示し、legacy compile結果を変更しない。
- Overviewには0.4のResource、identity、World、Protocol、Handler、Law数を追加する。

## 6. Artifacts and API

Studio HTTP `/api/state`は次を追加する。

```json
{
  "glyph04_views": {
    "schema": "glyph.studio-views",
    "version": 1,
    "enabled": true,
    "summary": {},
    "views": {}
  }
}
```

Studio専用ViewModelであり、Glyph 0.4 Public IR schemaには追加しない。Public IRを置換せず、UI向けprojectionとして扱う。

## 7. Non-goals

今回の実装には含めない。

- diagramからGlyph sourceを書き換えるround-trip editing
- concrete Host runtimeの実行・simulation
- runtime eventのlive streaming
- View間の選択同期とcross-highlight
- 大規模設計向けlayout engine
- Protocolのmessage timing simulation
- Law違反traceのinteractive replay

これらはcanonical identityとsource mapを利用する次段階として追加できる。

## 8. Acceptance conditions

- 同じtyped designから七つのviewを一回だけ構築する。
- plain sourceでは0.4 viewを無効化する。
- complete 0.4 exampleで七つ全てのview dataが生成される。
- Protocol eventはdirection、type、structured pathを保持する。
- Resource viewはsymbolic identity単位でstateを表示する。
- compile error時に最後の有効viewを失わない。
- `manual.rs`を上書きしない。
- package root API、Public IR schema、legacy生成物を変更しない。
- Python tests、stabilization、main compatibility、Rust tests、Clippyが成功する。

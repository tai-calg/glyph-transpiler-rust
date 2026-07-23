# Glyph Live Language System

## 1. Purpose

Glyphを単なる一方向transpilerではなく、Reader、Compiler、Loader、Runtimeが同じ実行環境内に常駐し、検証済み定義を実行中Imageへ反映できる言語へ発展させる。

目標はphaseを消すことではない。

```text
Read      text -> syntax
Expand    syntax -> expanded syntax
Compile   syntax -> code
Load      code -> World Patch
Run       code -> value / effect
```

各phaseの意味と保証は分離する。一方、呼出し方向を固定した一回限りのpipelineにはしない。

```text
Reader   -> evaluate reader extension
Compiler -> read / expand / evaluate compile-time code
Runtime  -> read / compile / load extension code
```

今回の実装は、この再入可能な言語系を安全に成立させるための最初の実行基盤として、Versioned World、Definition Cell、World Patch、transactional commitを追加する。

## 2. Scope implemented in this stage

実装済み:

- immutable `DefinitionVersion`
- versioned `LiveWorld`
- stable `Definition Cell` history
- typed `WorldPatch`
- reload safety classification
- old Worldを保持する`WorldLease`
- atomic function-body hot swap
- quiescence待ち
- migration-required patchの停止
- Reader/macro generation変更の停止
- compile error時のlast committed World保持
- Glyph Studio Previewとの接続
- Live Image Studio view
- `/api/live/state`
- `/api/live/commit`
- `/api/live/discard`
- `live-image.json`
- standalone `glyph_live.py` launcher

まだ実装しない:

- generated Rust function pointerのprocess内差替え
- native/JIT code object loader
- Runtimeからの一般的な`read/expand/compile/eval`
- user-defined reader macro evaluator
- compile-time effect sandbox
- Resource instanceの自動migration
- Protocol participant間のversion negotiation
- distributed/process間World commit
- runtime Law traceとの統合

この区別は重要である。今回のLive Imageは**定義・生成code handle・安全条件を管理する意味runtime**であり、任意のRust stack frameやGPU kernelを直接書き換えるmechanismではない。

## 3. Architecture

```text
Editor / file watcher / runtime extension request
    ↓
IncrementalCompiler
    ↓
validated typed design + generated code
    ↓
Live definition extraction
    ↓
Candidate World
    ↓
World diff
    ↓
World Patch
    ├─ hot-swap
    ├─ quiescence
    ├─ migration
    └─ reader
    ↓
transactional commit
    ↓
Active World generation
```

Studio integration:

```text
Glyph source typing
    ↓
/api/preview
    ↓
compile succeeds
    ↓
LiveImage.stage(...)
    ↓
commit or pending patch
    ↓
Live Image view
```

Compile failureの場合、Editor sourceとdiagnosticだけを更新し、Active Worldは変更しない。

## 4. World model

`LiveWorld`は一つの有効な言語Image世代を表す。

```text
LiveWorld
    version
    parent_version
    source_digest
    semantic_digest
    code_digest
    definitions[]
```

Worldはcommit後に変更しない。

```text
World 1
    inc -> definition digest A

World 2
    inc -> definition digest B
```

既存実行は`WorldLease(1)`を保持できる。新しい実行はActive World 2を取得する。これにより、実行途中のcall graphを強制的に別世代へ切り替えない。

## 5. Definition Cell

Definition Cellは名前に対する変更可能なslotではなく、World世代ごとのimmutable定義履歴である。

```text
function:inc
    World 1 -> digest A
    World 2 -> digest B
```

具体的なruntime bindingは将来のHostが選択する。

```text
native function pointer
JIT code handle
Wasm component export
actor command ID
manager registry handle
interpreter closure
```

Glyph Compilerは`Arc`, `Weak`, `RwLock`, Tokio等を選ばない。

## 6. Canonical definition extraction

Live ImageはGlyph sourceを再parseしない。Compilerのvalidated typed designと内部`CompilationModel`から定義を抽出する。

Public typed-design JSONはlegacy積型・直和型・aliasの完全な構造を意図的に公開していないため、Live Studioは同じcompile transactionで得られた内部modelを使用する。これによりPublic IRを変更せず、field・variant・alias target変更をmigrationとして検出できる。

対象:

- typed function body and signature
- effect / opaque boundary signature
- product / sum / aliasの完全な型構造
- Capability aggregate
- Resource declaration and state set
- World
- Protocol
- Handler
- Law
- Machine
- raw macro / AST macro / reader extension
- temporal specification

Function dependencyはtyped expression内のresolved `symbol_id`から導出する。文字列検索や表示順から依存を推測しない。

## 7. Reload safety lattice

```text
hot-swap < quiescence < migration < reader
```

これは性能順位ではなく、commit前に必要な条件の強さである。

### 7.1 hot-swap

対象:

- typed function signatureが同じ
- function bodyだけが変化
- 新しいfunction definition cellの追加

動作:

- Candidate Worldを即時commit
- 旧World leaseは継続可能
- 新規実行は新Worldを見る

### 7.2 quiescence

対象:

- World意味変更
- Protocol意味変更
- Handler意味変更
- Law意味変更
- Machine意味変更
- temporal specification変更

動作:

- active base Worldにleaseがある間はPending
- leaseが0になった時点で自動commit
- definition contentは変更せずWorld単位で切り替える

### 7.3 migration

対象:

- function signature変更
- type/aggregate変更
- Resource state set変更
- definition削除

動作:

- 自動commitしない
- `migration-plan-required` blockerを付ける
- 明示的なmigration planなしではAPIもcommitを拒否する

現段階ではmigration planは監査用説明文字列であり、自動状態変換codeではない。将来はtyped migration functionとResource obligationへ置換する。

### 7.4 reader

対象:

- raw macro変更
- AST macro変更
- reader generation変更

動作:

- 現在のread transactionには適用しない
- `reader-generation-acknowledgement-required` blockerを付ける
- 明示承認後、次のread transactionから新世代を使う

Reader自身を新Readerで読み直す循環を避けるため、Reader変更は必ず旧Readerで読み、transactionalに次世代へcommitする。

## 8. Patch model

```text
WorldPatch
    id
    base_world
    target_world
    source_digest
    semantic_digest
    code_digest
    definitions
    changes
    blockers
```

各change:

```text
definition_id
kind
name
added / modified / removed
safety
reason
source line
affected dependents
```

Patch IDは内容digestから決定し、走査順や時刻に依存しない。

## 9. Commit invariants

1. commit対象patchの`base_world`は現在のActive Worldである。
2. Worldはcommit後immutableである。
3. function body hot swapはtyped signature一致時だけ自動commitする。
4. quiescence patchはbase World leaseが0になるまでcommitしない。
5. migration patchは非空migration planなしにcommitしない。
6. Reader patchは明示acknowledgementなしにcommitしない。
7. compile failureはActive WorldとPending Patchを破壊しない。
8. old World leaseはnew World commit後も同じWorldを参照する。
9. Compiler Public IR schemaは変更しない。
10. concrete ownership/synchronization/runtime表現をCompilerが選択しない。

## 10. Studio behavior

Live Studio launcher:

```bash
python3 glyph_live.py path/to/design.glyph
```

StudioのAuto previewまたはPreviewを実行すると、完成して検証に成功したsource snapshotだけがLive Imageへstageされる。

Live Image view:

- Active World
- parent World
- definition count
- source/code digest
- Pending Patch
- safety class
- blockers
- affected dependents
- running World leases
- Definition Cell history
- World history

MigrationまたはReader blockerを持つpatchはUIで明示確認を要求する。

## 11. HTTP API

### `GET /api/live/state`

Live Image stateを返す。

### `POST /api/live/commit`

```json
{
  "migration_plan": "No live Buffer values; restart device region",
  "reader_acknowledged": true
}
```

不要なfieldは省略可能。必要条件を満たさない場合はHTTP 409。

### `POST /api/live/discard`

Pending Patchを破棄し、Active Worldを維持する。

## 12. Relation to Host Binding

Live ImageとHost Bindingは別責務である。

```text
Host Requirement
    Hostが提供すべき意味操作

Host Invocation
    programが操作を要求する位置

Live Image
    どの定義世代をactiveにするか

Concrete Host
    code handle、scheduler、transport、resource migrationの実装
```

将来、Host Invocation loweringが実装された後、Definition Cellのactive code handleがHost callとpure function dispatchの入口になる。

## 13. Next implementation stages

### R12-1: typed migration

- `migrate(old:T@WorldN):T@WorldN+1`
- Resource identity preservation
- success/failure migration obligation
- rollbackable migration transaction

### R12-2: phase services

- `read`
- `expand`
- `compile`
- `load`
- `eval`
- phase-specific Capability
- compile-time effect audit

### R12-3: code loader

- generated code object abstraction
- Host-selected native/JIT/Wasm/interpreter binding
- Definition Cell dispatch
- safe point integration

### R12-4: runtime trace

- invocation lifecycle events
- World version on every event
- Law monitor replay
- cross-version Protocol trace

## 14. Acceptance conditions

- function body edit commits a new World without terminating an old World lease
- function signature change remains pending
- legacy product/sum/alias shape changes remain pending
- Resource state change requires migration plan
- World/Protocol/Handler/Law changes wait for quiescence
- Reader change requires acknowledgement
- compile error retains last committed World
- Preview does not save the source file
- `live-image.json` is available
- Live Image UI injection remains syntactically valid
- ordinary `GlyphStudio` behavior remains unchanged
- legacy compiler output remains byte-compatible
- Python tests, Glyph 0.4 stabilization, Rust tests, demos, and Clippy pass

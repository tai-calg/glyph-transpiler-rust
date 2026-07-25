# Checked System Context and explicit boundaries

この文書は、Glyph 0.4における`system`、`ext`、`!`、通常関数、`machine`の責務を定義する。

旧仕様の`system Name=entry`と、entryからcall graphを自動的にSystem Contextへ転用する設計は廃止された。

## 1. 基本原則

```text
system   システム境界、公開port、主要なデータ・戻り値・作用flow
machine  呼出しをまたいで意味を持つドメイン状態
>        一回の同期処理、純粋計算、分岐、処理順序
ext      外部所有の入力・provider境界
!        システムから外部へ要求する作用境界
```

System Flowとcall graphは同じではない。

```text
code call: control -> sensor
data flow: sensor -> control
```

`system`は前者を生成する命令ではなく、後者を含むArchitecture assertionである。コンパイラは、宣言された各edgeに型付きコード証拠を付与できる場合だけ受理する。

## 2. 正規構文

```glyph
system DoorController
  entry control

  in state:DoorState
  in sensor:Input
  out receipt:Receipt

  state -> control
  sensor -> control
  control -> receipt
  control -> lock
  control -> alarm
```

必須要素:

1. `entry`は本体を持つ`>`関数である。
2. 一つ以上の`in` portを持つ。
3. R1では一つの`out` portを持つ。
4. すべてのendpointはportまたは宣言済みsymbolへ解決される。
5. すべてのedgeはコードから証明可能である。

次は拒否される。

```glyph
system DoorController=control
```

診断は、新しい`system` blockへの移行方法を示す。

## 3. 境界の極性

### 外部入力

```glyph
ext sensor():Input|ControlError
```

- 所有者はシステム外部である。
- System Context上の主方向はoutside → systemである。
- Glyph本体を持たない。
- 未宣言名を`ext`として推定しない。

### 外部作用

```glyph
!lock(state:DoorState):Receipt|ControlError
!alarm(state:DoorState):Receipt|ControlError
```

- システムが外部へ作用を要求する境界である。
- System Context上の主方向はsystem → outsideである。
- Host adapterが実装を所有する。

### 手書きRust依存

```glyph
~layout_lane(input:BatchInput):BatchLayout
```

`~`は論理上純粋だが、実装をRust側へ委譲する依存である。System Contextへ含める場合は明示edgeを宣言する。

## 4. 一回の実行とReceipt

新しい`runtime`宣言子は導入しない。一回の実行順序は通常関数で記述する。

```glyph
>control(state:DoorState):Receipt|ControlError
  input := sensor()?
  next := step(state,input)
  apply(next)
```

```glyph
>apply(state:DoorState):Receipt|ControlError
  state.action==RaiseAlarm >> alarm(state)
  _ >> lock(state)
```

意味:

```text
external input
  -> pure decision and state transition
  -> exactly one selected external effect
  -> confirmed Receipt or typed ControlError
```

`Receipt`は単なる要求受付ではなく、Hostが外部作用の完了を確認した結果として型設計する。受付だけを表す場合は`Acknowledgement`など別型を使用する。

## 5. edgeと証拠

ArchitectureIRはedgeごとに証拠を保存する。

| edge | kind | 必要な証拠 |
|---|---|---|
| caller port → entry | `data` | entry parameter名と型 |
| ext port → function | `data` | external input readへの到達pathと成功型 |
| function → out port | `return` | 正常戻り型とentryからの到達性 |
| function → `!` | `effect` | effect boundaryへの到達pathと引数型 |
| function → function / `~` | `responsibility` | 宣言済みcall path |

edgeは実行コードを生成しない。コードとArchitectureの整合性を要求する。

## 6. 検査

コンパイラは少なくとも次を拒否する。

- 未宣言entry
- 未宣言endpoint
- 未宣言の到達可能call
- `ext`を出力作用として使う極性逆転
- `!`を入力providerとして使う極性逆転
- port型と関数型の不一致
- コードに存在しないedge
- 到達可能な外部入力または作用境界の記載漏れ
- 一つのguard branchから複数effectを実行する構造
- output portへ到達しないentry

Glyphの短縮型`U/B/F/I`と正規化後の`u16/bool/f32/i16`は、System Context型検査で同じcanonical typeとして扱う。

## 7. View分離

Studioと生成artifactは次を分ける。

```text
Checked System Context
  public boundary and semantic flow

Call Graph
  implementation call dependency

Machine
  persistent domain-state transition

Outcome / Logic
  one-call evaluation and failure paths
```

明示`system`がある場合、内部helperをSystem Contextへ自動混入させない。境界へ接続されていない宣言は別の`Internal and unconnected declarations` viewへ置く。

I/O viewのsystem contract:

```json
{
  "kind": "checked-system-context",
  "entry": "control",
  "ports": [],
  "nodes": [],
  "edges": [],
  "evidence": []
}
```

edge labelは`data`、`returns`、`effect`、`flow`を使用する。`calls`はsystem宣言がない場合のderived call graphだけで使用する。

## 8. 保守性規則

- system blockはソース先頭へ置き、第三者が境界を先に読めるようにする。
- 主実行経路をraw macroへ隠さない。
- 永続状態だけを`machine` stateへ保持する。
- 一時的な判断結果はlocal bindingまたは専用値型にする。
- Host adapter、生成module、test controlsを無条件にpublicへしない。
- public facadeは利用者が必要な型と操作だけを再公開する。
- test専用の故障注入・観測関数はcrate内testへ閉じる。
- Example名、内容、Acceptance testの目的を一致させる。
- generated metadataや一時migration payloadをrepositoryへ残さない。

## 9. 非目標

`system` edgeは次を主張しない。

- schedulerやthread配置
- async task lifecycle
- process間transport
- branchが毎回実行されること
- 物理装置の停止性の形式証明

これらは専用IRまたはHost契約で扱う。`system`の保証は、表示された境界とflowが宣言済みsymbol、型、到達pathに対応することである。

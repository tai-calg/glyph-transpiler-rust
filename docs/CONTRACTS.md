# Glyph 0.4 — Capability, Resource and Kinded Contract Space

Glyph 0.4は、既存の短いGlyphを変更せず、必要な値と処理だけへ次の契約を追加する。

```text
Permission     誰が保持・参照・変更できるか
Resource       同一資源がどのstateにあるか
World          どの実行領域・動的Regionで有効か
Protocol       どの順序で値を交換するか
Handler        failure/time/cancel等をどう解釈するか
Law            trace全体が満たすべき性質
```

Contract名は通常の型・値名と字句的に分離する。

```glyph
Rpc          # 通常の型・値名
'Rpc         # Contract名
```

## 後方互換性

次を含まない既存sourceは従来経路をそのまま通る。

```text
resource
own / share / link / &mut / as
'Name
@{'Name}
```

Contract／Capability未使用時は、生成Rust、既存Typed Design JSONのshape、既存diagram file集合、`@NAME`／`@A`／`@E`の意味を変更しない。file単位のmodeも導入しない。

## Capability

```glyph
own T
share T
link T
&T
&mut T
```

| Capability | 意味 |
|---|---|
| `own T` | 唯一所有。代入・by-value引数でmove |
| `share T` | 明示複製可能な共有所有 |
| `link T` | 寿命を維持しない長期link |
| `&T` | 完全式内の一時読み取り |
| `&mut T` | 完全式内の一時排他変更 |

能力変換:

```glyph
shared := owner as share
copy := &shared as share
weak := &shared as link
other := &weak as link
live := (&weak as share)?
```

move後利用、borrow脱出、`share`／`link`からの`&mut`、`share -> own`、`own -> link`、不正な`as`を拒否する。

Compatibility Rust backendでは、Capability操作を静的検査した後、従来の値表現へ消去する。実際のArc／Weak／link livenessはHost adapterのtrusted contractであり、`verification-report.json`に明示する。

## Resource

```glyph
resource Buffer[
  Allocated
 |Ready
 |InFlight
 |Retired
]
```

resource使用時はCapabilityとstateを必ず明示する。

```glyph
own Buffer[Ready]
share Buffer[Ready]
link Buffer[Ready]
```

state遷移は`own Resource[S]`だけに許可する。`share`／`link` resourceのstateは固定し、`own Resource[S]`は全制御出口でreturn／transfer／transition／consumeされなければならない。失敗可能操作は失敗型にもresourceを保持する。

```glyph
resource Buffer[Ready|Used]
+E=Bad

*WriteError(
  buffer:own Buffer[Ready],
  cause:E
)

!write(
  buffer:own Buffer[Ready]
):own Buffer[Used]|WriteError
```

`resource-flow-ir.json`ではsuccessとfailureの両経路が同一`rho:write:buffer`を保持する。

## Contract定義と適用

```glyph
'@Name = ...    # World
'>Name = ...    # Protocol
'!Name = ...    # Handler
'?Name = ...    # Law
'Name  = {...}  # Bundle
```

参照は`'Name`、適用は`@{'Name}`とする。`@{Name}`のようなbare nameは認めない。

## World

Worldは実行locusと動的Regionの積である。

```glyph
'@UiWindow =
  Ui * App/Window

'@WorkerTask =
  Worker * App/Window/Task
```

異なるlocus間のProtocolなし直接call、異なるWorldへのborrow転送、狭いRegionの`own`／`share`を広いRegionのfieldへ保存するescapeを拒否する。`link`による長期観測は許可する。

Hostは宣言locusへのdispatchとRegion生成・終了を実装する。

## Protocol

```text
()          end
-> T        callerから実行側へTを送る
<- T        実行側からcallerへTを返す
P >> Q      sequence
P | Q       choice
P || Q      parallel
*P          repeat
```

```glyph
'>RequestReply =
  -> Request >> <- Response

'>Events =
  *(<- Event)
```

旧記法`>T`／`<T`は、関数宣言や比較演算との衝突を避けるため拒否する。Protocol構文、Bundle内競合、関数署名との互換性、cross-World borrow、Protocolなしcross-World callを検査する。

Transport、buffer、ordering等の具体実装はProtocol traceを満たすHost adapterまたはLaw Contractへ置く。

## Handler

Handlerは予約語の列挙ではなく、`'std.*` Contract APIの合成として記述する。

```glyph
'!RequestPolicy =
  'std.timeout(2s)
  >> 'std.retry(
       3,
       'std.exponential,
       'std.idempotent
     )
  >> 'std.return_error
```

標準operation:

```text
'std.timeout(Duration)
'std.cancel(...)
'std.retry(Count,Backoff,Idempotency)
'std.rollback(place)
'std.compensate(effect)
'std.fallback(function)
'std.return_error
```

retry count、idempotency、Result型、resource failure ledger、rollback対象、compensation境界、fallback署名、最終recoveryの一意性を検査する。業務上の真の冪等性や物理rollback成功はtrusted contractとして報告する。

## Law

Lawは既存の`@A`／`@E`時相論理を再利用する。

```glyph
'?Safe =
  @A(!fault >> stopped)

'?Deadline =
  @A(start >> @E 2s finish)
```

Productへ適用したLawは既存reference monitor／streaming monitorへ接続する。

```glyph
'Observed = {'Safe}

*Observation(
  fault:B,
  stopped:B
) @{'Observed}
```

関数lifecycle Lawは`runtime-contract-ir.json`へ保持し、Host lifecycle event monitorの義務として出力する。

## Bundle

```glyph
'WorkerCall = {
  'WorkerTask,
  'RequestReply,
  'RequestPolicy,
  'Deadline
}
```

World、Protocol、Handlerは各最大1個、Lawは複数可とする。Handler順序はBundle列挙順へ依存させずHandler定義内で明示する。Bundle循環を拒否する。

## 生成IR

Glyph 0.4を使用した場合だけ次を追加生成する。

```text
capability-ir.json
resource-flow-ir.json
contracts-ir.json
runtime-contract-ir.json
verification-report.json
```

`verification-report.json`は保証を次へ分類する。

```text
static     コンパイラが決定的に検査
model      時相式／modelで検査
runtime    生成monitorまたはHost monitorで検査
trusted    Host adapter・設計者が満たす証明義務
```

新構文を使わないsourceではこれらを生成しない。

## 完全例

[`examples/acceptance/glyph04_system.glyph`](../examples/acceptance/glyph04_system.glyph)は、Capability、resource state、World、Region、Protocol、timeout／retry Handler、Product Law monitor、Bundle、Rust生成、0.4 Public IRを一つのsourceで接続する。

CIは同sourceについて決定的再生成と生成Rustの`rustc` compileを行う。

## 意図的な境界

Glyph 0.4は設計契約と静的検査を実装する。thread／executor、channel／network transport、timer／cancel primitive、Arc／Weak、物理resource解放、DB transaction／compensationの実作用はHost側に残す。

CPU core affinity、scheduler priority、NUMA／物理メモリ配置、authentication／authorization、database isolation、replica／quorum／distributed consistency、一般的deadlock freedom、定量性能保証は0.4の保証対象外とする。

これらを`queue`、`strong`、`eventual`等の曖昧な予約語として追加せず、将来もWorld／Protocol／Handler／LawのContract libraryとして拡張する。

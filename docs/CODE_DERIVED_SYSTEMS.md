# Executable System boundary

この文書は、Glyphにおける`system`、`entry`、`source`、`sink`、`ext`、`!`、通常関数、`machine`の責務を定義する。

## 1. 基本原則

```text
system   外部から見える完全な関数実行境界
entry    外部からinvokeされるSystem内の通常関数
source   Systemが呼び出して外部から値を取得するext関数
sink     Systemが呼び出して外部作用を要求する!関数
machine  呼出しをまたいで意味を持つドメイン状態
>        System内の通常関数、純粋計算、分岐、処理順序
ext      外部所有のpull型入力関数
!        外部作用関数
```

System図のノードは関数だけである。型、値、戻り値名を独立ノードへしない。

System図の矢印は常に次の一義的な意味を持つ。

```text
caller ─calls→ callee
```

データの向き、戻り値の向き、作用の向きを同じ矢印へ混在させない。引数型、正常戻り型、失敗型は関数ノードのシグネチャとして表示する。

## 2. 正規構文

```glyph
system DoorController
  entry control
  source sensor
  sink lock
  sink alarm
```

Systemブロックで宣言するのは関数名と境界上の役割だけである。

- `entry`は一つだけ必要
- `source`と`sink`はゼロ個以上
- `entry`は本体を持つ`>`関数
- `source`は`ext`関数
- `sink`は`!`関数
- 型は各関数宣言から導出
- 呼出し関係は関数本体から導出

次の値portと手書きedgeは正規構文では使用しない。

```glyph
in state:DoorState
out receipt:Receipt
state -> control
control -> receipt
```

旧`in`、`out`、`->`は移行中のソースを読み込むためだけに残る。ArchitectureIRやStudio図の正当性を与える根拠にはならない。

次も廃止されている。

```glyph
system DoorController=control
```

## 3. entry

```glyph
>control(state:DoorState):Receipt|ControlError
  input := sensor()?
  next := step(state,input)
  apply(next)
```

```glyph
system DoorController
  entry control
```

`control`はSystem内部に実装され、外部へ公開されるinvoke点である。

```text
outside ─invoke→ control
```

`control`の引数がSystemへの同期入力、完全な戻り型がSystemの同期応答になる。

```text
input   state: DoorState
output  Receipt | ControlError
```

正常型だけを取り出して失敗型を消してはならない。

## 4. source

```glyph
ext sensor():Input|ControlError
```

```glyph
system DoorController
  source sensor
```

`source`はSystemが外部関数を呼び、値を取得するpull型境界である。

```text
control ─calls→ sensor
sensor  ─returns→ Input | ControlError
```

ポーリング、センサー読出し、設定取得などが該当する。

割り込み、コールバック、メッセージ受信ハンドラのように外部側がSystemをinvokeする入口は`source`ではない。同期的な公開入口として扱える場合は`entry`、非同期eventを独立分類する場合は将来の専用宣言で扱う。

## 5. sink

```glyph
!lock(state:DoorState):Receipt|ControlError
!alarm(state:DoorState):Receipt|ControlError
```

```glyph
system DoorController
  sink lock
  sink alarm
```

`sink`はSystemが外部関数を呼び、外部作用を要求する境界である。

```text
apply ─calls→ lock
apply ─calls→ alarm
```

戻り値が存在しても、呼出し主導権と作用方向がSystemから外部なので`sink`に分類する。

`Receipt`は要求受付ではなく、Hostが外部作用の完了を確認した結果として設計する。受付だけを表す場合は`Acknowledgement`など別型を使用する。

## 6. 導出される実行図

次の実装を考える。

```glyph
>authenticate(input:Input):B=input.badge_valid&!input.forced_open

>decide(input:Input):Action
  input.forced_open >> RaiseAlarm
  authenticate(input)&input.request_open >> Unlock
  _ >> KeepLocked

>step(state:DoorState,input:Input):DoorState
  action := decide(input)
  ...

>apply(state:DoorState):Receipt|ControlError
  state.action==RaiseAlarm >> alarm(state)
  _ >> lock(state)

>control(state:DoorState):Receipt|ControlError
  input := sensor()?
  next := step(state,input)
  apply(next)
```

コンパイラは`entry control`から到達可能な呼出しを追跡し、次を導出する。

```text
control
├── sensor          source
├── step            internal
│   └── decide      internal
│       └── authenticate
└── apply           internal
    ├── alarm       sink
    └── lock        sink
```

値型の`Input`、`DoorState`、`Receipt`、`ControlError`は関数ノードの入出力欄へ表示し、独立ノードにはしない。

## 7. 完全性検査

コンパイラは次を拒否する。

- 未宣言entry
- `entry`に`ext`または`!`を指定する
- `source`に通常関数または`!`を指定する
- `sink`に通常関数または`ext`を指定する
- entryから到達不能なsourceまたはsink
- entryから到達するのにSystemへ宣言されていないsource
- entryから到達するのにSystemへ宣言されていないsink
- 未宣言の到達可能call
- 同じ関数を複数の境界役割へ割り当てる
- source名とentry引数名が衝突し、関数と値を区別できない構造
- 一つのguard branchから複数の外部作用を実行する構造

内部関数はSystemブロックへ列挙しない。entryからの実行経路として自動導出する。

## 8. ArchitectureIR

ArchitectureIRは関数ノードとcall edgeだけを公開する。

```json
{
  "name": "DoorController",
  "entry": "control",
  "sources": ["sensor"],
  "sinks": ["lock", "alarm"],
  "ports": [],
  "components": [
    {"name": "control", "kind": "function", "role": "entry"},
    {"name": "sensor", "kind": "external", "role": "source"},
    {"name": "lock", "kind": "effect", "role": "sink"}
  ],
  "edges": [
    {"kind": "call"}
  ]
}
```

各call edgeには、呼出し元、呼出し先、ソース行を示す証拠を付ける。

旧port/edge相当の情報を必要とする内部意味解析には、関数シグネチャから導出したprovenance metadataを渡す。これはユーザーが手書きするArchitectureではなく、コンパイラ内部の証明事実である。

## 9. Studio表示

StudioのSystem viewは次の役割を明示する。

```text
ENTRY     外部からinvokeされる通常関数
SOURCE    Systemが読むext関数
SINK      Systemが呼ぶ!関数
INTERNAL  entryから到達する内部関数
```

すべての矢印ラベルは`calls`になる。

各関数ノードには次を表示する。

- 関数名
- 境界役割
- 引数名と型
- 正常型と失敗型を含む完全な戻り型
- ソース行

## 10. 非目標

`system`は次を直接表さない。

- schedulerやthread配置
- process間transport
- async task lifecycle
- interrupt controllerの設定
- branchが毎回実行されること
- Host実装や物理装置の正しさの形式証明

これらは専用IRまたはHost契約で扱う。`system`が保証するのは、宣言した境界関数が正しい種類で存在し、entryからの完全な実行call graphと一致することである。

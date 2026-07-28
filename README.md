# Glyph

Glyphは、ソフトウェア設計のうち、**型、判断、状態、外部境界、資源、安全条件**を短いコードへまとめ、同じ意味モデルから次を生成する設計DSLです。

- Rustコード
- I/O構成図
- 状態遷移図
- 処理フロー図
- 時間制約の解析・監視情報
- 機械処理用JSON / IR

Glyphはアプリケーションの細部をすべて実装する言語ではありません。OS、デバイス、通信、実時計測、GPU処理などはHost実装へ残し、設計レビューで確認したい構造を明示します。

> 現在のバージョンは`0.4.0`、開発段階はAlphaです。本番システムへ導入する場合は、生成コードとHost実装を必ずレビューしてください。

---

## 1. Glyph Studio

左側でGlyphコードを編集し、右側でコンパイラが導出した図を確認できます。図は手書きのメタデータではなく、検証済みの型、関数、`system`、`machine`から生成されます。

### 状態遷移図

Motor Safetyの状態、初期遷移、到達可能・到達不能状態、入力・ガード・遷移結果を一画面へ表示しています。

![Glyph Studioの状態遷移図](docs/images/glyph-studio-state-transition.jpg)

### I/O構成図

Door Controllerの入力、代表関数、戻り値、外部作用を、コード上の型と呼出し根拠に基づいて表示しています。

![Glyph StudioのI/O構成図](docs/images/glyph-studio-io.jpg)

---

## 2. Glyphで解決する問題

一般的な設計資料では、図、文章、実装コードが別々に管理されます。実装を変更しても図が更新されず、資料とコードが一致しなくなることがあります。

Glyphでは設計を一つの`.glyph`ファイルへまとめます。

```text
Glyphソース
   ├── 型とデータ構造
   ├── 純粋な計算
   ├── 条件分岐
   ├── 外部入力と外部作用
   ├── システム境界
   ├── 状態遷移
   ├── 資源・所有・Protocol
   └── 時間制約
          ↓
   Rust / 図 / JSON / 診断 / witness
```

**純粋な計算**は、ファイル書込み、ネットワーク通信、GPIO操作などを行わず、入力から出力を計算する処理です。

**外部作用**は、プログラム外部の状態を変更し得る処理です。モーター駆動、ファイル保存、通信送信などが該当します。

---

## 3. 最短で試す

### 3.1 必要な環境

- Python 3.10以上
- Rustコードをビルドする場合はRust toolchain
- Desktop版を開発する場合はNode.jsとTauriの開発環境

### 3.2 起動

```bash
git clone https://github.com/tai-calg/glyph-transpiler-rust.git
cd glyph-transpiler-rust
python3 glyph.py
```

ファイルを指定せず起動すると、`.glyph/workspace.glyph`を開きます。ファイルが存在しない場合だけサンプルを作成し、既存ファイルは上書きしません。

既存ファイルを開く場合:

```bash
python3 glyph.py examples/acceptance/door_controller.glyph
```

開発用インストール:

```bash
python3 -m pip install -e .
glyphc design.glyph --check
```

Rustと図を生成:

```bash
python3 glyphc.py design.glyph \
  -o build/generated.rs \
  --host-output build/host.generated.rs \
  --diagram-dir build/diagrams \
  --ast-json build/typed-ast.json
```

### 3.3 Desktop版

```bash
cd desktop
npm install
npm run dev
```

macOSの配布用アプリをビルドする場合は、リポジトリ直下から次を実行します。

```bash
./desktop/scripts/build_macos_app.sh
```

---

## 4. 最初のGlyphコード

```glyph
*Input(badge_valid,request_open,forced_open:B)

+Action=KeepLocked|Unlock|RaiseAlarm
+Mode=Locked|Unlocked|Alarmed

*DoorState(mode:Mode,action:Action)

>decide(input:Input):Action
  input.forced_open >> RaiseAlarm
  input.badge_valid & input.request_open >> Unlock
  _ >> KeepLocked

>step(state:DoorState,input:Input):DoorState
  action := decide(input)
  action == RaiseAlarm >> DoorState(Alarmed,RaiseAlarm)
  action == Unlock >> DoorState(Unlocked,Unlock)
  _ >> DoorState(Locked,KeepLocked)
```

読み方:

1. `*Input(...)`で入力データを定義する
2. `+Action=...`と`+Mode=...`で取り得る選択肢を定義する
3. `>decide(...)`で入力から操作を選ぶ
4. `>step(...)`で現在状態と入力から次状態を計算する
5. ガード列は上から評価し、最初に成立した`条件 >> 値`を選ぶ
6. `_`は、それまでの条件に一致しなかった場合を表す

完全な例は[`examples/acceptance/door_controller.glyph`](examples/acceptance/door_controller.glyph)を参照してください。

---

## 5. 文法を読むための基本規則

Glyphはコード量を抑えるため、一部の記号を構文位置に応じて使い分けます。まず、次の三分類を区別してください。

| 分類 | 例 | 誰が決めるか |
|---|---|---|
| 予約構文 | `?`, `*`, `>>`, `@A`, `@E` | Glyph言語 |
| ユーザー定義名 | `Input`, `lock_deadline`, `forced_open` | 設計者 |
| リテラル | `500ms`, `true`, `42` | ソースに直接書く値 |

### 5.1 時間制約の分解

```glyph
?lock_deadline(*Input) =
  @A(unlocked >> @E 500ms locked)
```

| 部分 | 分類 | 意味 |
|---|---|---|
| `?` | 予約記号 | 時間制約宣言の開始 |
| `lock_deadline` | ユーザー定義名 | 制約名 |
| `*Input` | 予約記号＋ユーザー定義型 | `Input`のfieldを観測式へ展開 |
| `=` | 予約記号 | 宣言と定義式の区切り |
| `@A` | 予約演算子 | always |
| `unlocked` | ユーザー定義field | `Input.unlocked`に由来する観測値 |
| `>>` | 予約演算子 | 左が成立した場合に右へ進む |
| `@E` | 予約演算子 | eventually |
| `500ms` | 時間リテラル | 500ミリ秒以内 |
| `locked` | ユーザー定義field | `Input.locked`に由来する観測値 |

この式は次を意味します。

```text
常に、
unlockedが観測されたなら、
500ms以内にlockedが成立しなければならない。
```

`unlocked`や`locked`は予約語ではありません。次の型で設計者が定義したfieldです。

```glyph
*Input(unlocked,locked:B)
```

### 5.2 `>>`の共通意味

`>>`は、どの文脈でも**左側が成立・完了した場合に右側へ進む**ことを表します。

```glyph
# ガード列: 条件が成立したら右側の値を選ぶ
input.forced_open >> RaiseAlarm

# 時間制約: 左の命題が成立したら右の命題を要求する
forced_open >> alarmed

# Protocol / Handler: 左の手順の後に右の手順へ進む
send_request >> receive_response
```

文脈ごとの違いは右側の種類です。

| 文脈 | 左側 | 右側 | 評価 |
|---|---|---|---|
| ガード列 | bool条件 | 任意型の結果 | 上から最初に成立した行を選ぶ |
| 時間制約 | 命題 | 命題 | 論理含意として評価する |
| Protocol / Handler | 手順 | 次の手順 | 順序関係を表す |

同じ記号を使う根拠は`if / then`または「次へ進む」という共通した読み方です。文法上の意味が完全に同一という主張ではありません。

### 5.3 文脈で役割が決まる記号

| 記号 | 使用位置 | 意味 |
|---|---|---|
| `?` | 行頭の`?name(...)` | 時間制約宣言 |
| `?` | 式の後ろ`call()?` | Resultの失敗伝播 |
| `*` | 行頭`*Input(...)` | 積型宣言 |
| `*` | 引数位置`*Input` | 積型fieldの展開 |
| `*` | Protocol内`*P` | 手順Pの繰返し |
| `|` | `+Mode=A|B` | 直和variantの区切り |
| `|` | 戻り値`T|E` | `Result<T,E>`の短縮 |
| `|` | 式`P|Q` | 論理和 |
| `|` | `|x| expr` | ラムダ引数の囲み |
| `|` | Protocol内`P|Q` | 手順の選択 |
| `=` | 宣言・定義位置 | 名前と定義の区切り |
| `==` | 式 | 等値比較 |
| `!` | 行頭`!write(...)` | 外部作用宣言 |
| `!` | 式`!condition` | 論理否定 |
| `'!` | Contract宣言 | Handler Contract |
| `@` | `@MAX`, `@limit(...)` | raw / ASTマクロ宣言 |
| `@A`, `@E` | 時間制約 | always / eventually |
| `@{'Contract}` | 宣言への付加 | Contract適用 |
| `->` | `system`内 | 公開境界上のflow |
| `-> T`, `<- T` | Protocol内 | 送信方向 / 受信方向 |
| `'Name` | Contract位置 | Contract名 |
| `Name` | 通常位置 | 型・関数・値などのObject名 |

コンパイラは構文位置から区別します。READMEの標準例では、複合演算子の前後に空白を入れ、境界を視認しやすくします。

```glyph
# 推奨
@A(forced_open >> alarmed)
input.valid & input.ready >> Accept

# 読みにくいため標準例では使用しない
@A(forced_open>>alarmed)
input.valid&input.ready>>Accept
```

---

## 6. トップレベル文法

| 記法 | 名前 | 目的 |
|---|---|---|
| `*Name(...)` | 積型 | 複数の項目を一つのデータへまとめる |
| `+Name=A|B` | 直和型 | 値が取り得る選択肢を列挙する |
| `=Name=Type` | 型別名 | 既存型表現へ別名を付ける |
| `>name(...)` | 純粋関数 | 入力から出力を計算する |
| `~name(...)` | Rust実装関数 | 型契約だけGlyphへ置く |
| `ext name(...)` | 外部入力 | システム外から値を受け取る |
| `!name(...)` | 外部作用 | システム外へ作用する |
| `system Name` | システム境界 | 公開I/Oと作用flowを宣言する |
| `machine Name(...)` | 状態機械 | 初期状態と次状態計算を宣言する |
| `?name(...)=...` | 時間制約 | 安全条件や期限を宣言する |
| `resource Name[...]` | 状態付き資源 | 資源状態と能力を検査する |
| `@NAME=...` | rawマクロ | 識別子単位の字句置換 |
| `@name(x)=...` | ASTマクロ | 式構造を保った展開 |
| `'...` | Contract | World、Protocol、Handler、Lawを付加する |

---

## 7. 型とデータ

### 7.1 基本型

| Glyph | Rust相当 |
|---|---|
| `u8`, `u16`, `u32`, `u64` | 符号なし整数 |
| `i8`, `i16`, `i32`, `i64` | 符号付き整数 |
| `f32`, `f64` | 浮動小数点数 |
| `bool` | 真偽値 |
| `String` | 文字列 |
| `R<T,E>` | `Result<T,E>` |
| `O<T>` | `Option<T>` |
| `V<T>` | `Vec<T>` |

短縮型:

| 短縮 | 正規型 |
|---|---|
| `F` | `f32` |
| `D` | `f64` |
| `U` | `u16` |
| `I` | `i32` |
| `B` | `bool` |
| `S` | `String` |

### 7.2 積型

```glyph
*SensorInput(value:F,valid:B,count:U)
*Point(x,y:F)
```

関数引数ではfieldを展開できます。

```glyph
*Sample(value:F,valid:B)
>check(*Sample):B=valid
```

### 7.3 直和型

```glyph
+Mode=Idle|Running|Faulted
+Command=Stop|Run(U)
+Event=Started{time:U}|Failed{code:U,message:S}
```

### 7.4 Result短縮

型シグネチャ最上位の`T|E`は`Result<T,E>`です。

```glyph
>parse(text:S):Value|ParseError
```

`T/E`と`T?E`は使用しません。

---

## 8. 関数、分岐、パイプライン

### 8.1 純粋関数

```glyph
>double(x:U):U=x*2

>finish(x:I):I
  y := x + 1
  y*2
```

最後の式が戻り値です。`return`という予約語は使用しません。

`:=`は可変代入ではなく、一度だけ定義するローカル束縛です。

### 8.2 ordered guard

```glyph
+Sign=Negative|Zero|Positive

>classify(x:I):Sign
  x < 0 >> Negative
  x == 0 >> Zero
  _ >> Positive
```

1. 上から条件を評価する
2. 最初に成立した行の値を返す
3. `_`は明示的なfallback
4. `_`は最後に置く

variantのpayloadも取り出せます。

```glyph
+Command=Stop|Run(U)

>speed(command:Command):U
  command == Stop >> 0
  command == Run(value) >> value
```

### 8.3 エラー伝播

```glyph
>control():Receipt|ControlError
  input := sensor()?
  next := step(input)
  apply(next)
```

式後置の`?`は成功値を取り出し、失敗時は関数全体からエラーを返します。

### 8.4 パイプラインとラムダ

```glyph
>run(value:U):U
  value
  /> normalize
  /> |x| x + 1
  /> clamp
```

`/>`は左側の値を右側の関数へ順番に渡します。Resultを返す段階には`?`を付けられます。

```glyph
input /> validate? /> decide
```

現在のパイプラインラムダは、一引数・一式・外側の実行時変数をcaptureしない純粋な範囲です。

---

## 9. Rust実装、外部入力、外部作用

```glyph
~shortest_path(graph:Graph,start:U,goal:U):Path

ext sensor():Input
ext database(query:Query):Record|DatabaseError

!write_motor(command:Command):Receipt|ControlError
!save_file(data:Data):Receipt|FileError
```

| 記法 | 本体 | 契約 |
|---|---|---|
| `>` | Glyph | 純粋 |
| `~` | `manual.rs` | 純粋であることをHost側が保証 |
| `ext` | Host | outside → system |
| `!` | Host | system → outside、外部状態を変更し得る |

`manual.rs`は利用者が編集する安定した置換点です。自動生成される`generated.rs`は直接編集しません。

---

## 10. System Context

`system`は外部から見える入力、出力、作用の関係を宣言します。自由な作図命令ではありません。

```glyph
system MotorSafety
  entry cycle

  in state:MotorState
  in input:Input
  out receipt:Receipt

  state -> cycle
  input -> cycle
  cycle -> receipt
  cycle -> write_motor
```

コンパイラは次を確認します。

- endpointが宣言済みの型・関数・作用へ解決される
- port型が一致する
- edgeにコード上の根拠がある
- 到達可能な外部入力と作用が境界へ表れる

`System Context`と内部call graphは別の関係です。

```text
System Context: input -> cycle -> receipt / write_motor
Call graph:     cycle -> step -> decide -> normalize
```

---

## 11. 状態機械

```glyph
machine Motor(state:MotorState,input:Input)
  select=state.mode
  init=MotorState(Stopped,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted
```

| 項目 | 意味 |
|---|---|
| `select` | 状態を表すfieldまたは式 |
| `init` | 初期状態 |
| `next` | 次状態を計算する式 |
| `success` | 正常終了として強調する状態 |
| `failure` | 失敗として強調する状態 |

状態遷移図には、初期状態、状態、遷移、入力、ガード、作用、成功・失敗経路、到達不能状態、静的解析警告が表示されます。

`machine`が存在しない場合、型名や関数名から状態機械を推測しません。

---

## 12. 時間制約

```glyph
?forced_open_safe(*Input) =
  @A(forced_open >> alarmed)

?lock_deadline(*Input) =
  @A(unlocked >> @E 500ms locked)
```

| 記法 | 意味 |
|---|---|
| `!P` | Pではない |
| `P & Q` | PかつQ |
| `P | Q` | PまたはQ |
| `P >> Q` | PならばQ |
| `@A P` | Pが常に成立する |
| `@E P` | Pがいつか成立する |
| `@E 500ms P` | Pが500ms以内に成立する |
| `P U Q` | Qが成立するまでPが成立し、Qは必ず成立する |
| `P W Q` | Qが成立するまでPが成立する。Qが成立しなくてもよい |
| `@A@E 1s P` | 常に、1秒以内に再びPが成立する |
| `@E@A P` | いつか以降、常にPが成立する |

裸の`A`、`E`、`AE`、`EA`、旧記号`□`、`◇`は使用しません。

実時計測、イベント供給、周期実行、違反後の復旧はHost側の責任です。

---

## 13. マクロ

### rawマクロ

```glyph
@MAX=100
@CONTROL=write_motor(step(state,input).command)

>cap(value:U):U=min(value,MAX)
```

大文字名を完全な識別子単位で置換します。`IN`を定義しても`Input`や`MIN`の一部は置換しません。

複数行:

```glyph
@NORMALIZE
  normalized := input.raw
  normalized /> |x| min(x,MAX)
@end
```

### ASTマクロ

```glyph
@limit(x,high)=min(x,high)
>run(x:U):U=limit(x,100)
```

循環参照はエラーです。`A`と`E`は時相演算子用のためrawマクロ名として予約されています。

---

## 14. CapabilityとResource

### Capability

| 記法 | 意味 |
|---|---|
| `own T` | 一つの所有者が保持する |
| `share T` | 複数箇所から共有できる |
| `link T` | 所有せず参照先を指す |
| `&T` | 一時的に読み取る |
| `&mut T` | 一時的に排他的に書き換える |

```glyph
>checksum(buffer:&Buffer):U
>clear(buffer:&mut Buffer):B
```

Capability変換:

```glyph
shared := owner as share
weak := &shared as link
live := (&weak as share)?
```

`as`は一般のデータ変換やResource状態変更には使用できません。

### Resource

```glyph
resource Buffer[Allocated|Ready|InFlight|Retired]

!submit(buffer:own Buffer[Ready]):own Buffer[InFlight]
```

失敗経路でも所有Resourceを失わない場合、エラー値へ資源を含めます。

```glyph
*WriteError(buffer:own Buffer[Ready],cause:Error)
!write(buffer:own Buffer[Ready]):own Buffer[Used]|WriteError
```

---

## 15. Contract

Contractは通常の型や関数へ、実行場所、通信手順、失敗処理、法則を付加する上級機能です。

| 宣言 | 種類 | 目的 |
|---|---|---|
| `'@Name=...` | World | 実行場所と領域 |
| `'>Name=...` | Protocol | 値の送受信順序 |
| `'!Name=...` | Handler | timeout、retry、rollback |
| `'?Name=...` | Law | 守るべき時間・安全条件 |
| `'Name={...}` | Bundle | 複数Contractをまとめる |

```glyph
'@WorkerTask=Worker * App/Window/Task

'>RequestReply=
  -> Request
  >> <- Response

'!RequestPolicy=
  'std.timeout(2s)
  >> 'std.retry(3,'std.exponential,'std.idempotent)
  >> 'std.return_error

'?Deadline=@A(start >> @E 2s finish)
```

Bundleと適用:

```glyph
'WorkerCall={
  'WorkerTask,
  'RequestReply,
  'RequestPolicy,
  'Deadline
}

!process(image:own Image[Ready]):ProcessResult
  @{'WorkerCall}
```

実際のthread、executor、transport、timer、取消、retry、rollback、compensationはHost側で実装します。

---

## 16. 理論的基盤と保証範囲

Glyphは複数の理論を一つの設計体験へ接続しています。ただし、**理論に由来する構造を実装していること**と、**Glyphコンパイラや生成システム全体が形式証明済みであること**は同じではありません。

### 16.1 実装状況の読み方

| 表記 | 意味 |
|---|---|
| 実装 | コンパイラが構文・型・構造を検査する |
| 部分実装 | 対応可能な部分集合だけを保守的に解析する |
| 設計基盤 | 言語・IR設計の根拠だが、一般法則は証明しない |
| Host依存 | 実行時の保証をHost実装が担う |
| 未対応 | 現在の保証範囲外 |

### 16.2 分野別の対応

| 分野 | 理論的な基盤 | 現在の実装 | まだカバーしない範囲 |
|---|---|---|---|
| 積型・直和型 | 代数的データ型 | 型宣言、型検査、Rust struct / enum生成 | 一般再帰型の完全解析、ABI同値性 |
| Result / Option | 型付き失敗・部分性 | 型検査、`?`伝播、Rust生成 | 一般的なeffect system |
| 型代数 | 型の和・積を半環として扱う考え方 | 対応可能な有限型の正規化、要素数、構造変換、witness | field名の業務意味、浮動小数、再帰型、所有権を含む一般同型 |
| 純粋関数と作用境界 | 純粋計算とeffectの分離 | `>` / `~` / `ext` / `!`の境界 | `~`やHost実装の純粋性証明 |
| 状態機械 | FSM / labelled transition system | 初期状態、遷移IR、guard coverage、到達可能性、scenario witness | 階層状態、直交状態、fairness、一般的な無限状態model checking |
| 時間制約 | LTL系の時相論理、有限trace semantics | `@A`, `@E`, bounded eventually, `U`, `W`, 三値判定、streaming monitorの部分集合 | `X`、一般formula progression、無限trace完全検証、WCET |
| Capability / Resource | affine・linear type、ownership、typestate | move / borrow / state / symbolic identityの静的検査 | Rust borrow checkerの完全代替、soundness theorem、deadlock検査 |
| Protocol | session type / communicating processの考え方 | 方向、順序、choice、parallel構造の検査・IR | transport実行、distributed conformance、通信障害の完全検証 |
| Contract / Law | design by contract、runtime verification | 要求IR、静的整合性、monitor要求、verification strength | 一般Hoare logic、SMT証明、定理証明 |
| モノイダル構造 | tensor、独立な合成 | 積構造、複数Capability、純粋で独立と判断できるlaneのIR | thread・async・GPU並列実行の保証、圏の法則の一般証明 |
| System Context | typed architecture / data-flow | endpoint解決、型整合、code evidence、図生成 | 外部装置・network・driverの正しさ |
| Rust・図・IR生成 | 意味保存変換の工学的設計 | 同一validated modelからの決定的生成、回帰試験 | compiler correctnessや完全なsemantic preservationの形式証明 |

### 16.3 強く裏付けられている範囲

現在、比較的明確に理論と実装が対応しているのは次です。

- 積型・直和型とRustのstruct / enum
- Result / Optionと型付き失敗経路
- 有限な積・和型の半環的な正規化
- 明示された状態機械の遷移構造
- 対応可能な有限・整数領域のcoverageと到達可能性
- 有限trace上の一部時相式
- Capability、Resource、Typestateの静的な構造検査
- コード根拠を要求するSystem Context
- 同一意味モデルからの決定的なRust・IR・図生成

### 16.4 部分対応またはHost依存の範囲

次は理論的な方向性がありますが、Glyphだけでは完結しません。

- 実時間deadlineの物理的達成
- async、thread、scheduler、queue
- transport、timeout、retry、rollback、compensation
- Lawへのruntime event供給
- Resourceの実際の格納・破棄・device ownership
- `~`で実装したRust、GPU kernel、`unsafe`
- センサー、actuator、driver、OS、hardwareの正しさ
- 並列候補を実際に並列実行するschedule

### 16.5 現在主張できること

- 対応構文の型・名前・境界整合性を検査する
- 純粋計算と外部作用の境界を明示する
- 状態遷移を構造化し、対応範囲でcoverageと到達可能性を解析する
- 対応する時相式を有限traceまたはruntime monitor用に変換する
- Capability、Resource、Protocol、Contract要求を機械処理可能なIRへする
- 同じvalidated modelからRust、JSON、図を決定的に生成する
- 生成物とwitnessを継続的な回帰試験へかける

### 16.6 現在主張できないこと

- システム全体にバグがない
- 全状態・全入力・全無限実行が検証済み
- deadlineを実機で必ず守る
- race、deadlock、starvationが存在しない
- 外部装置・network・driverが正しい
- compiler自体が形式証明済み
- Glyphと生成Rustの意味保存が機械証明済み
- ASIL、SIL、DO-178C等の認証要件を自動的に満たす
- 圏論、線形型、時相論理の一般法則をすべて証明する

Glyph 0.4は、**形式手法の考え方を実用的な設計、生成、診断へ接続するAlpha段階のツール**です。形式証明済み言語や認証済み開発環境として扱わないでください。

---

## 17. 生成物

設定と使用構文に応じて、次のファイルを生成します。

```text
generated.rs
host.generated.rs
manual.rs
architecture.mmd
architecture-ir.json
execution.mmd
execution-ir.json
machine-<name>.mmd
temporal.mmd
typed-ast.json
source-map.json
io-state-views.json
capability-ir.json
resource-flow-ir.json
contracts-ir.json
runtime-contract-ir.json
verification-report.json
type-algebra-ir.json
type-algebra-tooling.json
machine-coverage.generated.rs
machine-scenarios.generated.rs
```

すべてのファイルが常に生成されるわけではありません。対応する構文を使用した場合だけ生成されるIRがあります。

---

## 18. Glyph Studioの操作

### 編集

| 操作 | 意味 |
|---|---|
| `コンパイル` | 保存せず現在のコードを検査し、図を更新する |
| `保存` | ファイルへ保存して再コンパイルする |
| 自動プレビュー | 入力停止後に図を更新する |
| 診断欄 | 構文・型エラー、警告を表示する |

### 図

| 操作 | 結果 |
|---|---|
| 空白ドラッグ | キャンバス移動 |
| タッチパッドのピンチ | 拡大・縮小 |
| `−` / `＋` | 10%刻みの縮小・拡大 |
| `全体表示` | 図全体を表示領域へ収める |
| `表示を戻す` | 100%と初期位置へ戻す |
| ノードドラッグ | ノード位置を変更する |
| ラベルドラッグ | 遷移ラベル位置を調整する |
| ラベルをダブルクリック | 自動位置へ戻す |
| `Auto layout` | 保存位置を消して自動配置する |

倍率は25%から300%です。表示倍率はSVG、PNG、PDFの出力座標へ影響しません。

### テーマと出力

| 操作 | 結果 |
|---|---|
| `White` | 白基調 |
| `Monochrome` | 提出資料向け白黒 |
| `SVG` | ベクター画像 |
| `PNG` | 2倍解像度 |
| `PDF` | 横向きPDF |

---

## 19. よくある間違い

### 比較に`=`を使う

```glyph
x = 0   # 誤り
x == 0  # 正しい
```

### 演算子を詰めて読みづらくする

```glyph
@A(forced_open>>alarmed)     # 受理される場合があるが標準例では使用しない
@A(forced_open >> alarmed)   # 推奨
```

### 観測fieldを予約語だと思う

```glyph
*Input(unlocked,locked:B)
?deadline(*Input)=@A(unlocked >> @E 500ms locked)
```

`unlocked`と`locked`は`Input`で設計者が定義したfieldです。

### ガードの最後の`_`を省略する

```glyph
>sign(x:I):I
  x < 0 >> -1
  _ >> 1
```

### 時相演算子へ`@`を付けない

```text
@A safe       正しい
@E 1s ready   正しい
A safe        使用しない
◇ ready       使用しない
```

### `system`の矢印を自由な作図として使う

`system`のedgeは、実際の型、戻り値、呼出し、外部作用と一致する必要があります。

---

## 20. 開発とテスト

Python:

```bash
python3 -m unittest discover -s tests -v
```

Rust:

```bash
cargo test
```

主要CI:

- Pythonコンパイラテスト
- Glyph 0.4 stabilization / compatibility gate
- Rust生成、format、test、Clippy
- Public UI SDK
- Desktopビルド
- I/O図・状態遷移図のChromium回帰試験
- SVG、PNG、PDF出力
- Zoom、Fit、Reset
- ノード・ラベル編集と永続化

---

## 21. 文書一覧

| 目的 | 文書 |
|---|---|
| 言語仕様全体 | [`docs/LANGUAGE.md`](docs/LANGUAGE.md) |
| 時間制約 | [`docs/TEMPORAL.md`](docs/TEMPORAL.md) |
| Capability、Resource、Contract | [`docs/CONTRACTS.md`](docs/CONTRACTS.md) |
| I/O図と状態遷移図 | [`docs/IO_STATE_APP.md`](docs/IO_STATE_APP.md) |
| 図の編集と出力 | [`docs/DIAGRAM_EDITOR.md`](docs/DIAGRAM_EDITOR.md) |
| パイプラインとラムダ | [`docs/PIPELINE_DESIGN.md`](docs/PIPELINE_DESIGN.md) |
| rawマクロ | [`docs/PREPROCESSOR.md`](docs/PREPROCESSOR.md) |
| コンパイル処理と生成物 | [`docs/COMPILATION_PIPELINE.md`](docs/COMPILATION_PIPELINE.md) |
| 全文書の索引 | [`docs/README.md`](docs/README.md) |

---

## 22. ライセンス

MIT License。詳細は[`LICENSE`](LICENSE)を参照してください。

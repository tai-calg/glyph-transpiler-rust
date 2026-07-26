# Glyph

Glyphは、ソフトウェアの設計を短いコードで書き、同じ設計から次を生成するツールです。

- Rustコード
- I/O構成図
- 状態遷移図
- 処理の流れを示す図
- 時間制約の検証情報
- 機械処理しやすいJSON

Glyph自体は、アプリケーションの細部をすべて実装する言語ではありません。**型、判断、状態、外部との境界、安全条件など、設計レビューで確認したい部分を明示するための小さな言語**です。

> 現在のバージョンは`0.4.0`で、開発段階はAlphaです。本番システムへ導入する場合は、生成コードとHost実装を必ずレビューしてください。

---

## 1. Glyphで解決する問題

一般的な設計資料では、図、文章、実装コードが別々に管理されます。その結果、実装を変更しても図が更新されず、設計資料と実際のコードが一致しなくなることがあります。

Glyphでは、設計を一つの`.glyph`ファイルへまとめます。

```text
Glyphソース
   ├── 型とデータ構造
   ├── 純粋な計算
   ├── 条件分岐
   ├── 外部入力と外部作用
   ├── システム境界
   ├── 状態遷移
   └── 時間制約
          ↓
   Rust / 図 / JSON / 診断
```

ここでいう**純粋な計算**とは、ファイル書き込み、ネットワーク通信、GPIO操作などを行わず、入力から出力を計算する処理です。

ここでいう**外部作用**とは、プログラム外部の状態を変える処理です。例えば、モーター駆動、ファイル保存、通信送信などが該当します。

---

## 2. 最短で試す

### 2.1 必要な環境

- Python 3.10以上
- Rustコードをビルドする場合はRust toolchain
- Desktop版を開発する場合はNode.jsとTauriの開発環境

### 2.2 リポジトリから起動する

```bash
git clone https://github.com/tai-calg/glyph-transpiler-rust.git
cd glyph-transpiler-rust
python3 glyph.py
```

ファイルを指定せず起動すると、`.glyph/workspace.glyph`を開きます。ファイルが存在しない場合だけ、ドア制御のサンプルを自動作成します。既存ファイルは上書きしません。

### 2.3 既存ファイルを開く

```bash
python3 glyph.py examples/acceptance/door_controller.glyph
```

### 2.4 Pythonパッケージとして開発用インストールする

```bash
python3 -m pip install -e .
```

インストール後は、次のコマンドも使用できます。

```bash
glyphc design.glyph --check
```

### 2.5 Rustと図を生成する

```bash
python3 glyphc.py design.glyph \
  -o build/generated.rs \
  --host-output build/host.generated.rs \
  --diagram-dir build/diagrams \
  --ast-json build/typed-ast.json
```

---

## 3. 最初のGlyphコード

次は、入力に応じてドアを施錠、解錠、警報状態へ移す小さな例です。

```glyph
*Input(badge_valid,request_open,forced_open:B)

+Action=KeepLocked|Unlock|RaiseAlarm
+Mode=Locked|Unlocked|Alarmed

*DoorState(mode:Mode,action:Action)

>decide(input:Input):Action
  input.forced_open >> RaiseAlarm
  input.badge_valid&input.request_open >> Unlock
  _ >> KeepLocked

>step(state:DoorState,input:Input):DoorState
  action := decide(input)
  action==RaiseAlarm >> DoorState(Alarmed,RaiseAlarm)
  action==Unlock >> DoorState(Unlocked,Unlock)
  _ >> DoorState(Locked,KeepLocked)
```

このコードは次の順序で読めます。

1. `*Input(...)`で入力データを定義する
2. `+Action=...`で取り得る操作を定義する
3. `+Mode=...`で取り得る状態を定義する
4. `>decide(...)`で入力から操作を決める
5. `>step(...)`で現在状態と入力から次状態を決める

`>>`の左側が条件、右側が条件成立時の値です。`_`は、それまでの条件に一致しなかった場合を表します。

完全な例は[`examples/acceptance/door_controller.glyph`](examples/acceptance/door_controller.glyph)を参照してください。

---

## 4. 画面の使い方

`python3 glyph.py`で開く画面では、左側でGlyphコードを編集し、右側で図を確認します。

### 4.1 編集と保存

| 操作 | 意味 |
|---|---|
| `コンパイル` | ファイルへ保存せず、現在のコードを検査して図を更新する |
| `保存` | コードをファイルへ保存し、再コンパイルする |
| 自動プレビュー | 入力を止めてから一定時間後に図を更新する |
| 診断欄 | 構文エラー、型エラー、警告を表示する |

診断の表示言語は、設定画面から`日本語`または`English`を選択できます。初期設定は日本語です。

### 4.2 図の移動と拡大縮小

| 操作 | 結果 |
|---|---|
| 空白部分をドラッグ | キャンバスを上下左右へ移動する |
| `−` | 10%縮小する |
| `＋` | 10%拡大する |
| `全体表示` | 現在の表示領域へ図全体が収まる倍率にする |
| `表示を戻す` | 倍率を100%へ戻し、表示位置を初期位置へ戻す |
| `Ctrl`または`Command` + `+` | 拡大する |
| `Ctrl`または`Command` + `-` | 縮小する |
| `Ctrl`または`Command` + `0` | 表示を100%へ戻す |

倍率は25%から300%までです。`全体表示`を選択した状態では、ウィンドウサイズの変更に合わせて倍率を再計算します。

`表示を戻す`は表示倍率と表示位置だけを戻します。ノード配置を自動配置へ戻す操作とは異なります。

### 4.3 ノードとラベルの編集

| 操作 | 結果 |
|---|---|
| ノードをドラッグ | ノード位置を変更する |
| 通常ドラッグ | 8px単位で配置する |
| `Shift`を押しながらドラッグ | 1px単位で配置する |
| ノード選択後に矢印キー | 8px単位で移動する |
| `Shift` + 矢印キー | 1px単位で移動する |
| 遷移ラベルをドラッグ | ラベル位置を手動調整する |
| 遷移ラベルをダブルクリック | 手動位置を解除し、自動配置へ戻す |
| `Auto layout` | 保存済みノード位置を消し、自動配置へ戻す |

遷移ラベルは、矢印の中央付近を優先して配置されます。他のラベルや状態ノードと重なる場合は、探索範囲と表示幅を段階的に調整します。

### 4.4 テーマと出力

| 操作 | 結果 |
|---|---|
| `White` | 白基調の通常表示 |
| `Monochrome` | 会社資料へ貼りやすい白黒表示 |
| `SVG` | 拡大しても劣化しにくいベクター画像を出力する |
| `PNG` | 2倍解像度の画像を出力する |
| `PDF` | 横向きPDFを出力する |

図の表示倍率はエクスポート結果へ影響しません。エクスポートは図本来の座標とサイズを使用します。

### 4.5 設定の保存範囲

| 設定 | 保存先 | 保存期間 |
|---|---|---|
| 言語 | `localStorage` | ブラウザへ保持 |
| テーマ | `localStorage` | ブラウザへ保持 |
| ノード位置 | `localStorage` | ソースと図ごとに保持 |
| ラベル位置 | `localStorage` | ソースと図ごとに保持 |
| 倍率と表示位置 | `sessionStorage` | 同じブラウザタブを開いている間 |

---

## 5. 文法の全体像

Glyphのトップレベルでは、次の宣言を使用します。

| 記法 | 名前 | 目的 |
|---|---|---|
| `*Name(...)` | 積型 | 複数の項目を一つのデータへまとめる |
| `+Name=A|B` | 直和型 | 値が取り得る選択肢を列挙する |
| `=Name=Type` | 型別名 | 既存型へ別名を付ける |
| `>name(...)` | 純粋関数 | 入力から出力を計算する |
| `~name(...)` | Rust実装関数 | 型だけGlyphへ書き、本体をRustへ置く |
| `ext name(...)` | 外部入力 | センサーや外部サービスから値を受け取る |
| `!name(...)` | 外部作用 | ファイル、通信、装置などへ作用する |
| `system Name` | システム境界 | 公開する入力、出力、作用の関係を宣言する |
| `machine Name(...)` | 状態機械 | 状態の選択方法、初期状態、次状態を宣言する |
| `?name(...)=...` | 時間制約 | 常に守る条件や期限を宣言する |
| `resource Name[...]` | 状態付き資源 | 所有者と資源状態の変化を検査する |
| `@NAME=...` | rawマクロ | 字句置換する定数や式を定義する |
| `@name(x)=...` | ASTマクロ | 式の構造を保ったまま展開する |
| `'...` | Contract | 実行場所、通信、失敗処理、法則を追加する |

以下では、簡単な構文から順番に説明します。

---

## 6. コメント、名前、インデント

### 6.1 コメント

`#`から行末まではコメントです。

```glyph
# センサー値を正規化する
>normalize(value:F):F=min(value,1.0)
```

### 6.2 名前

型名は通常、大文字から始めます。

```text
Input
DoorState
ControlError
```

関数名と変数名は通常、小文字から始めます。

```text
decide
next_state
sensor
```

### 6.3 インデント

関数、`system`、`machine`などの内部はインデントして記述します。例では2空白を使用しています。

```glyph
>classify(x:I):I
  x<0 >> -1
  x==0 >> 0
  _ >> 1
```

---

## 7. 型

### 7.1 基本型

| Glyph | Rust相当 | 用途 |
|---|---|---|
| `u8`, `u16`, `u32`, `u64` | 符号なし整数 | 0以上の整数 |
| `i8`, `i16`, `i32`, `i64` | 符号付き整数 | 負数を含む整数 |
| `f32`, `f64` | 浮動小数点数 | 小数 |
| `bool` | 真偽値 | `true`または`false` |
| `String` | 文字列 | 文字列データ |
| `R<T,E>` | `Result<T,E>` | 成功値またはエラー |
| `O<T>` | `Option<T>` | 値ありまたは値なし |
| `V<T>` | `Vec<T>` | 同じ型の値の列 |

### 7.2 短縮型

| 短縮 | 正規型 |
|---|---|
| `F` | `f32` |
| `D` | `f64` |
| `U` | `u16` |
| `I` | `i32` |
| `B` | `bool` |
| `S` | `String` |

```glyph
*Point(x,y:F)
```

これは次と同じ意味です。

```glyph
*Point(x:f32,y:f32)
```

### 7.3 Result型の短縮

型シグネチャの最上位では、`T|E`を`Result<T,E>`として使用できます。

```glyph
>parse(text:S):Value|ParseError
```

`|`は書かれる場所によって意味が変わります。

| 場所 | 意味 |
|---|---|
| `T|E` | Result型 |
| `a|b` | 論理和 |
| `+Mode=Idle|Running` | variantの区切り |

---

## 8. データ型の宣言

### 8.1 積型 `*`

積型は、複数の項目を一つの値へまとめます。Rustの`struct`に近い役割です。

```glyph
*SensorInput(value:F,valid:B,count:U)
```

同じ型が続く場合は、項目名をまとめられます。

```glyph
*Point(x,y:F)
```

関数引数では、積型の項目を展開できます。

```glyph
*Sample(value:F,valid:B)
>check(*Sample):B=valid
```

### 8.2 直和型 `+`

直和型は、値が取り得る選択肢を列挙します。Rustの`enum`に近い役割です。

```glyph
+Mode=Idle|Running|Faulted
```

値を一つ持つvariant:

```glyph
+Command=Stop|Run(U)
```

名前付きの項目を持つvariant:

```glyph
+Event=Started{time:U}|Failed{code:U,message:S}
```

### 8.3 型別名 `=`

```glyph
=Output=Receipt|ControlError
```

型別名は新しいデータ構造を作るのではなく、既存の型表現へ名前を付けます。

---

## 9. 式と演算子

### 9.1 値と呼び出し

```glyph
42
true
input.value
normalize(input.value)
DoorState(Locked,KeepLocked)
Ok(receipt)
Err(ControlFailure)
```

### 9.2 算術

```text
a+b
a-b
a*b
a/b
-a
```

### 9.3 比較

```text
a<b
a<=b
a>b
a>=b
a==b
a!=b
```

`=`は定義、`==`は比較です。

```glyph
@MAX=100
>is_max(value:U):B=value==MAX
```

### 9.4 論理演算

```text
!condition     否定
left&right     論理積
left|right     論理和
```

### 9.5 組み込み値と関数

```text
Ok(value)
Err(error)
Some(value)
None
min(a,b)
max(a,b)
finite(value)
```

---

## 10. 純粋関数 `>`

### 10.1 一行関数

```glyph
>double(x:U):U=x*2
```

### 10.2 複数行関数

```glyph
>finish(x:I):I
  y := x+1
  y*2
```

最後の式が戻り値です。`return`という予約語は使用しません。

### 10.3 ローカル束縛 `:=`

`:=`は、関数内で計算結果へ名前を付けます。

```glyph
>control(state:State,input:Input):State
  command := decide(input)
  next := step(state,command)
  next
```

`:=`は比較ではありません。比較には`==`を使用します。

---

## 11. 条件分岐とパターン

Glyphでは`if`、`else if`、`else`という予約語を使用せず、上から順番に評価するガード列を使用します。

```glyph
+Sign=Negative|Zero|Positive

>classify(x:I):Sign
  x<0 >> Negative
  x==0 >> Zero
  _ >> Positive
```

評価規則は次の通りです。

1. 上から条件を評価する
2. 最初に成立した行の値を返す
3. `_`はそれまでの条件に一致しなかった場合を表す

フォールバックの`_`は最後に明示してください。

variantの中身も同じ記法で取り出せます。

```glyph
+Command=Stop|Run(U)

>speed(command:Command):U
  command==Stop >> 0
  command==Run(value) >> value
```

これは一般的な言語の`match`に相当します。

---

## 12. エラー伝播 `?`

Resultを返す式の後ろへ`?`を付けると、成功値を取り出し、失敗時は関数全体からエラーを返します。

```glyph
>control():Receipt|ControlError
  input := sensor()?
  next := step(input)
  apply(next)
```

`?`には二つの用途があります。

| 位置 | 意味 |
|---|---|
| 式の後ろ `sensor()?` | Resultの失敗伝播 |
| 行頭の宣言 `?deadline(...)=...` | 時間制約の宣言 |

構文位置が異なるため、コンパイラは両者を区別します。

---

## 13. パイプライン `/>`とラムダ

`/>`は、左側の値を右側の関数へ順番に渡します。

```glyph
>run(value:U):U
  value
  /> normalize
  /> clamp
```

これは概念的に次と同じです。

```glyph
clamp(normalize(value))
```

一時的な一引数関数はラムダで書けます。

```glyph
>run(value:U):U=
  value
  /> |x| x+1
  /> |x:U| min(x,100)
```

現在のパイプラインラムダには次の制限があります。

- 引数は一つ
- 式は一つ
- 外側の実行時変数を取り込まない
- 外部作用`!`を呼ばない
- 部分適用は行わない

Resultを返す段階には`?`を付けられます。

```glyph
input /> validate? /> decide
```

---

## 14. Rustへ実装を残す `~`

計算量、GPU処理、SIMD、`unsafe`、外部crate固有の処理などは、Glyphへ無理に書かず、型契約だけを`~`で宣言できます。

```glyph
*Graph(nodes:U,edges:U)
*Path(cost:U)

~shortest_path(graph:Graph,start:U,goal:U):Path # TODO: Rustで実装

>plan(graph:Graph,start:U,goal:U):Path=
  shortest_path(graph,start,goal)
```

`~`は純粋な計算として扱われますが、本体は`manual.rs`へ置きます。

| 記号 | 本体 | 外部状態を変更するか |
|---|---|---|
| `>` | Glyph | 変更しない |
| `~` | Rustの`manual.rs` | 変更しない契約 |
| `!` | Host実装 | 変更する可能性がある |

`manual.rs`は利用者が編集するファイルです。Glyphは初回作成後に上書きしません。自動生成される`generated.rs`は直接編集しないでください。

---

## 15. 外部入力 `ext`と外部作用 `!`

### 15.1 外部入力 `ext`

センサー、外部サービス、データベースなど、システム外部が所有する入力元を宣言します。

```glyph
ext sensor():Input
ext database(query:Query):Record|DatabaseError
```

### 15.2 外部作用 `!`

装置操作、通信送信、ファイル保存など、システム外部へ作用する処理を宣言します。

```glyph
!write_motor(command:Command):Receipt|ControlError
!save_file(data:Data):Receipt|FileError
```

試作用の式を付けることもできます。

```glyph
!send(value:U):U|Error=Ok(value)
```

### 15.3 方向の違い

```text
ext : outside -> system
!   : system -> outside
~   : system -> manual Rust implementation
```

---

## 16. システム境界 `system`

`system`は、利用者や外部装置から見える入力、出力、作用を宣言します。単なる関数呼び出し一覧ではありません。

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

各項目の意味:

| 項目 | 意味 |
|---|---|
| `entry cycle` | システムへ入る代表関数 |
| `in name:Type` | 外部から受け取る値 |
| `out name:Type` | 外部へ返す値 |
| `a -> b` | 公開境界上のデータ、戻り値、作用の関係 |

`system`内の矢印は、自由に図を描く命令ではありません。コンパイラは実際の型と関数呼び出しを確認し、根拠がある関係だけを受理します。

```text
System Context: input -> cycle -> receipt / write_motor
Call graph:     cycle -> step -> decide -> normalize
```

`System Context`は外部から見える構成、`call graph`は内部関数の呼び出し関係です。この二つは区別されます。

旧構文`system Name=entry`は使用しません。

---

## 17. 状態機械 `machine`

`machine`は、状態遷移図を生成するための宣言です。

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

状態遷移図には次が表示されます。

- 初期状態
- 取り得る状態
- 状態間の矢印
- 条件とアクション
- 成功状態と失敗状態
- 到達不能状態
- 静的解析警告

`machine`が存在しない場合、コンパイラは型名や関数名から状態機械を推測しません。

---

## 18. 時間制約 `?`

時間制約は、「常に守る」「いつか成立する」「一定時間以内に成立する」などの条件を記述します。

```glyph
?forced_open_safe(*Input)=@A(forced_open>>alarmed)
?lock_deadline(*Input)=@A(unlocked>>@E 500ms locked)
```

### 18.1 演算子

| 記法 | 意味 |
|---|---|
| `!P` | Pではない |
| `P&Q` | PかつQ |
| `P|Q` | PまたはQ |
| `P>>Q` | PならばQ |
| `@A P` | Pが常に成立する |
| `@E P` | Pがいつか成立する |
| `@E 500ms P` | Pが500ms以内に成立する |
| `P U Q` | Qが成立するまでPが成立し、Qは必ず成立する |
| `P W Q` | Qが成立するまでPが成立する。Qが成立しなくてもよい |

組み合わせも使用できます。

```glyph
@A@E 1s heartbeat
@E@A stable
```

裸の`A`、`E`、`AE`、`EA`や、旧記号`□`、`◇`は使用しません。

時間制約の実時計測、イベント供給、復旧処理はHost側の責任です。

---

## 19. マクロ `@`

### 19.1 一行rawマクロ

大文字名のrawマクロは、完全な識別子単位で置換します。

```glyph
@MAX=100
@CONTROL=write_motor(step(state,input).command)
```

使用時は`@`を付けません。

```glyph
>cap(value:U):U=min(value,MAX)
```

`IN`を定義しても、`Input`や`MIN`の一部分は置換しません。

### 19.2 複数行rawマクロ

```glyph
@NORMALIZE
  normalized := input.raw
  normalized /> |x| min(x,MAX)
@end
```

### 19.3 ASTマクロ

ASTマクロは、文字列ではなく式の構造として引数を展開します。

```glyph
@limit(x,high)=min(x,high)
>run(x:U):U=limit(x,100)
```

循環参照するマクロはエラーになります。

`A`と`E`は時相演算子に使用するため、rawマクロ名として予約されています。

---

## 20. 所有と資源

この章の構文は必要な場合だけ使用します。通常の型だけで設計する場合、必須ではありません。

### 20.1 Capability

Capabilityは、「その値を誰が保持し、誰が読み書きできるか」を型へ追加します。

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

`own`値を値渡しすると、元の変数からは使用できなくなります。

```glyph
next := owner
```

### 20.2 Capability変換

```glyph
shared := owner as share
copy := &shared as share
weak := &shared as link
other := &weak as link
live := (&weak as share)?
```

一般のデータ変換や、資源状態の変更へ`as`を使用することはできません。

### 20.3 Resource

Resourceは、状態変化を追跡する必要がある資源です。

```glyph
resource Buffer[Allocated|Ready|InFlight|Retired]
```

使用時はCapabilityと状態を指定します。

```glyph
own Buffer[Ready]
share Buffer[Ready]
link Buffer[Ready]
```

所有者だけが資源状態を変更できます。

```glyph
!submit(buffer:own Buffer[Ready]):own Buffer[InFlight]
```

失敗経路でも所有資源を失わないように、エラー型へ資源を含めます。

```glyph
*WriteError(buffer:own Buffer[Ready],cause:Error)
!write(buffer:own Buffer[Ready]):own Buffer[Used]|WriteError
```

---

## 21. Contract

Contractは、通常の型や関数へ、実行場所、通信手順、失敗処理、法則を追加する上級機能です。

通常の型や関数名を**Object名**、先頭に`'`が付く名前を**Contract名**として区別します。

```text
Image       通常の型
'Image      Contract
```

### 21.1 Contractの種類

| 宣言 | 種類 | 目的 |
|---|---|---|
| `'@Name=...` | World | 実行場所と領域を示す |
| `'>Name=...` | Protocol | 値の送受信順序を示す |
| `'!Name=...` | Handler | timeout、retry、rollbackなどを示す |
| `'?Name=...` | Law | 守るべき時間・安全条件を示す |
| `'Name={...}` | Bundle | 複数Contractをまとめる |

### 21.2 World

```glyph
'@WorkerTask=Worker * App/Window/Task
```

`Worker`が実行場所、`App/Window/Task`が動的な領域の経路です。実際のthread、executor、通信方式はHost側で実装します。

### 21.3 Protocol

```glyph
'>RequestReply=-> Request >> <- Response
```

| 記法 | 意味 |
|---|---|
| `()` | 通信終了 |
| `-> T` | 呼び出し側から実行側へTを送る |
| `<- T` | 実行側から呼び出し側へTを返す |
| `P>>Q` | Pの後にQ |
| `P|Q` | 選択 |
| `P||Q` | 並行構成 |
| `*P` | 繰り返し |

### 21.4 Handler

```glyph
'!RequestPolicy=
  'std.timeout(2s)
  >> 'std.retry(3,'std.exponential,'std.idempotent)
  >> 'std.return_error
```

認識される標準操作には、次があります。

```text
'std.timeout(Duration)
'std.cancel(...)
'std.retry(Count,Backoff,Idempotency)
'std.rollback(place)
'std.compensate(effect)
'std.fallback(function)
'std.return_error
```

実際のtimer、取消処理、業務上の冪等性、rollback処理はHost側で実装します。

### 21.5 Law

```glyph
'?Deadline=@A(start>>@E 2s finish)
```

### 21.6 Bundleと適用

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

Contract参照には先頭の`'`が必要です。`@{WorkerCall}`ではなく`@{'WorkerCall}`と書きます。

詳細は[`docs/CONTRACTS.md`](docs/CONTRACTS.md)を参照してください。

---

## 22. 文法一覧

次は、主要構文を形式的にまとめたものです。これは読み方を把握するための概要であり、厳密な仕様は[`docs/LANGUAGE.md`](docs/LANGUAGE.md)を参照してください。

```text
program              := top-level-item*

top-level-item       := raw-macro
                      | ast-macro
                      | product
                      | sum
                      | alias
                      | function
                      | rust-function
                      | external-input
                      | external-effect
                      | system
                      | machine
                      | temporal-spec
                      | resource
                      | contract

raw-macro            := "@" UPPER_NAME "=" expression
                      | "@" UPPER_NAME NEWLINE block "@end"
ast-macro            := "@" name "(" parameters? ")" "=" expression

product              := "*" TypeName "(" fields? ")"
sum                  := "+" TypeName "=" variant ("|" variant)*
alias                := "=" TypeName "=" type

function             := ">" signature ("=" expression | NEWLINE function-block)
rust-function        := "~" signature
external-input       := "ext" signature
external-effect      := "!" signature ("=" expression)?

function-block       := binding* (guard-list | expression)
binding              := name ":=" expression
guard-list           := guard+
guard                 := (expression | "_") ">>" expression

pipeline             := expression ("/>" pipeline-stage)+
pipeline-stage       := name "?"?
                      | "|" name (":" type)? "|" expression

system               := "system" TypeName NEWLINE system-item+
system-item          := "entry" name
                      | "in" name ":" type
                      | "out" name ":" type
                      | name "->" name

machine              := "machine" TypeName "(" parameters? ")" NEWLINE machine-item+
machine-item         := "select=" expression
                      | "init=" expression
                      | "next=" expression
                      | "success=" name
                      | "failure=" name

temporal-spec        := "?" name "(" parameters? ")" "=" formula
resource             := "resource" TypeName "[" name ("|" name)* "]"
capability-type      := ("own" | "share" | "link" | "&" | "&mut") type

contract             := "'@" ContractName "=" world
                      | "'>" ContractName "=" protocol
                      | "'!" ContractName "=" handler
                      | "'?" ContractName "=" formula
                      | "'" ContractName "=" "{" contract-reference* "}"
contract-reference   := "'" ContractName
contract-application := "@{" contract-reference ("," contract-reference)* "}"

formula              := implication
implication          := or-formula (">>" implication)?
or-formula           := and-formula ("|" and-formula)*
and-formula          := until-formula ("&" until-formula)*
until-formula        := unary-formula (("U" | "W") unary-formula)*
unary-formula        := "!" unary-formula
                      | "@A" unary-formula
                      | "@E" duration? unary-formula
                      | "(" formula ")"
                      | atom
```

---

## 23. 生成物

コンパイル設定に応じて、次のファイルを生成します。

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
```

すべてのファイルが常に生成されるわけではありません。対応する構文を使用した場合だけ生成されるIRがあります。

ここでいう**IR**はIntermediate Representationの略で、コンパイラが設計内容を機械処理しやすい形へ整理した中間表現です。

---

## 24. Glyphが保証する範囲

Glyphの検査結果は、次の区分で扱います。

| 区分 | 意味 |
|---|---|
| `static` | コンパイル時に検査できる |
| `model` | 状態や時間のモデルとして解析する |
| `runtime` | 実行時イベントを監視して確認する |
| `trusted` | Host実装または設計者が保証する必要がある |

Glyphが自動的に決めないもの:

- thread数とscheduler
- async runtime
- queueの実装
- 実際のtimer
- device driver
- `Arc`、`Weak`などの具体的なRust格納方式
- network transport
- 物理装置のrollback
- 業務上の冪等性
- GPU kernelや`unsafe`の正しさ

これらはHost側で実装し、生成される契約と検証報告に照らして確認します。

---

## 25. よくある間違い

### `=`で比較する

```glyph
x=0   # 誤り
x==0  # 正しい
```

### ガードの最後の`_`を省略する

```glyph
>sign(x:I):I
  x<0 >> -1
  _ >> 1
```

### Result型へ`T/E`や`T?E`を使用する

```text
T|E     推奨短縮
R<T,E>  正規表現
T/E     使用しない
T?E     使用しない
```

### 時相演算子へ`@`を付けない

```text
@A safe       正しい
@E 1s ready   正しい
A safe        使用しない
◇ ready       使用しない
```

### 外部入力を未宣言のまま呼ぶ

```glyph
ext sensor():Input
>read():Input=sensor()
```

### `system`の矢印を自由な作図として使用する

`system`の関係は、実際の型、戻り値、呼び出し、外部作用と一致する必要があります。

---

## 26. 開発とテスト

Pythonテスト:

```bash
python3 -m unittest discover -s tests -v
```

Rustテスト:

```bash
cargo test
```

Desktop版:

```bash
cd desktop
npm install
npm run dev
```

主要なCIでは、次を検査します。

- Pythonコンパイラテスト
- Rust生成とRustテスト
- Public UI SDK
- Desktopビルド
- I/O図と状態遷移図のブラウザ回帰テスト
- SVG、PNG、PDF出力
- 拡大、縮小、全体表示、表示リセット
- ノードとラベルのドラッグ

---

## 27. 文書一覧

| 目的 | 文書 |
|---|---|
| 言語仕様全体 | [`docs/LANGUAGE.md`](docs/LANGUAGE.md) |
| 初期の短縮構文 | [`docs/COMPACT_SYNTAX.md`](docs/COMPACT_SYNTAX.md) |
| I/O図と状態遷移図 | [`docs/IO_STATE_APP.md`](docs/IO_STATE_APP.md) |
| 図の編集と出力 | [`docs/DIAGRAM_EDITOR.md`](docs/DIAGRAM_EDITOR.md) |
| パイプラインとラムダ | [`docs/PIPELINE_DESIGN.md`](docs/PIPELINE_DESIGN.md) |
| 条件分岐とRust実装境界 | [`docs/RUST_TODO.md`](docs/RUST_TODO.md) |
| rawマクロ | [`docs/PREPROCESSOR.md`](docs/PREPROCESSOR.md) |
| 時間制約 | [`docs/TEMPORAL.md`](docs/TEMPORAL.md) |
| Capability、Resource、Contract | [`docs/CONTRACTS.md`](docs/CONTRACTS.md) |
| コンパイル処理と生成物 | [`docs/COMPILATION_PIPELINE.md`](docs/COMPILATION_PIPELINE.md) |
| 全文書の索引 | [`docs/README.md`](docs/README.md) |

---

## 28. ライセンス

MIT License。詳細は[`LICENSE`](LICENSE)を参照してください。

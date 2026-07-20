# Glyph 500文字ソフトウェアスケッチ 設計書

## 1. 目的

Glyphを、詳細実装前の約10分・500文字程度の記述から、次の4つを同時に把握できるソフトウェア設計DSLへ拡張する。

1. **Architecture** — 何が存在し、どこからどこへ情報・制御が流れるか
2. **State** — どこから始まり、どう遷移し、どこで正常・異常終了するか
3. **Logic** — どの条件で何を選ぶか
4. **Time** — 常に守る条件、期限内に成立すべき条件は何か

通常利用は次の1コマンドだけとする。

```bash
python3 glyph.py door.glyph
```

Studio内で、編集、保存、検査、Rust生成、図更新を同一プロセスで行う。

---

## 2. 設計原則

### 2.1 圧縮より対応関係を優先する

短く書けても、1行に複数の意味を詰め込みすぎない。

Architectureの標準形は**1接続1行**とする。

```glyph
system Door
  sensor -> ctl
  panel -> ctl
  ctl -> lock
  ctl -> log
```

これは次の図とほぼ1対1で対応する。

```text
sensor ─┐
        ├─> ctl ─> lock
panel ──┘      └─> log
```

`a,b -> c`のような圧縮形は将来許可してもよいが、formatterとREADMEが出す標準形にはしない。

### 2.2 名前を揃えることでbinding記法を消す

`system`内のcomponent名と、同名の関数・作用境界・型を自動的に結び付ける。

```glyph
system Door
  sensor -> ctl
  ctl -> lock

>ctl(input:Input):Command=...
!lock(command:Command):Receipt
```

解決規則:

1. 同名の`>`関数があれば pure function component
2. 同名の`!`境界があれば effect component
3. 同名の型があれば data component
4. どれにも一致しなければ external/conceptual component

これにより、`ctl:step`や`lock:!lock`のような補助記法を通常は不要にする。

### 2.3 名前が必要なロジックと不要なロジックを分ける

- 図の主要ノードになる処理: 名前付き関数
- 一度しか使わない局所変換: ラムダ式
- 外部作用: 名前付き`!`境界
- 再利用する判断: 名前付き関数またはASTマクロ

---

## 3. 目標例

```glyph
system Door
  sensor -> ctl
  panel -> ctl
  ctl -> lock
  ctl -> log

*In(open,auth,stop:B)
+Mode=Idle|Open|Locked|Fault
*State(mode:Mode)

>ctl(s:State,i:In):State
  i.stop >> State(Fault)
  !i.auth >> State(Locked)
  i.open >> State(Open)
  _ >> State(Idle)

!lock(m:Mode):B
!log(m:Mode):B

machine Door(state:State,input:In)
  select=state.mode
  init=State(Idle)
  next=ctl(state,input)
  success=Locked
  failure=Fault

?safe(*In)=A(!auth >> !open)
```

この1ファイルから次を生成する。

```text
Architecture  sensor/panel -> ctl -> lock/log
State         Idle/Open/Locked/Fault
Logic         stop, auth, openの優先分岐
Time          未認可時にopen禁止
Rust          型、関数、effect stub、monitor
```

---

## 4. `system`宣言

### 4.1 文法

```ebnf
system_decl = "system" IDENT NEWLINE system_edge+ ;
system_edge = INDENT endpoint "->" endpoint NEWLINE ;
endpoint    = IDENT ;
```

R1では1行に1本のedgeだけを書く。

```glyph
system Door
  sensor -> ctl
  panel -> ctl
  ctl -> lock
  ctl -> log
```

### 4.2 意味

`system`は実際のRust call graphではなく、設計上の責任・情報・制御の流れを表す。

```text
Architecture edge != function call
```

実際の関数呼出しは既存のExecutionStructureIRから別に取得する。

### 4.3 静的検査

- system名の重複
- 同一edgeの重複
- self-edge
- component名と複数symbol kindの曖昧な一致
- 未接続component
- `system`に現れるeffectが実際には`>`関数だった場合のrole表示

未解決componentはエラーにせず、`external`として表示する。

---

## 5. Architecture IR

```text
ArchitectureIR
├── systems: ArchitectureSystem[]
└── source_map

ArchitectureSystem
├── id: SymbolId
├── name
├── components: ArchitectureComponent[]
└── edges: ArchitectureEdge[]

ArchitectureComponent
├── local_id
├── name
├── kind: external | function | effect | data | conceptual
├── binding: SymbolId?
└── source: SourceRef

ArchitectureEdge
├── from
├── to
└── source: SourceRef
```

`binding`は文字列ではなく、既存SemanticModelの`SymbolId`を参照する。

---

## 6. Studioの4ビュー

### Architecture

`system`をそのままcomponent diagramとして表示する。

### State

`machine`から次を表示する。

- initial
- transition
- success terminal
- failure terminal

### Logic

名前付き純粋関数のguard treeを表示する。

```text
input
├─ condition 1 -> result 1
├─ condition 2 -> result 2
└─ otherwise   -> fallback
```

### Time

`?`制約を次の列へ正規化する。

```text
name | trigger | obligation | deadline | finish semantics
```

---

## 7. ラムダ式

### 7.1 現在の状態

現在実装済みなのは、名前付き純粋関数を`Fn<...>`型の値として渡す機能までである。

```glyph
>inc(x:U):U=x+1
>apply(f:Fn<U,U>,x:U):U=f(x)
>run(x:U):U=apply(inc,x)
```

匿名ラムダ式はまだ実装されていない。

### 7.2 導入目的

ラムダ式の主目的は、単なる値変数の削減ではなく、**一度しか使わない小関数の名前、宣言、参照をまとめて消すこと**である。

名前付き関数:

```glyph
>clamp(x:U):U=min(x,1000)
>run(x:U):U=apply(clamp,x)
```

ラムダ:

```glyph
>run(x:U):U=apply(|n|min(n,1000),x)
```

削減されるもの:

- `>clamp`という宣言
- `clamp`という名前を考える負担
- 宣言位置と利用位置の距離
- 一度しか使わないsymbol

### 7.3 採用構文

Rustに近く、ASCIIで入力できる次を採用する。

```glyph
|x|x+1
|x,y|x+y
|x:U|x+1
```

推奨formatter出力:

```glyph
|x| x+1
|x,y| x+y
```

`|`は既存の論理和にも使うが、式の先頭に`| parameter-list |`が現れた場合だけlambdaとして解析できる。

### 7.4 文法

```ebnf
lambda_expr   = "|" lambda_params? "|" expression ;
lambda_params = lambda_param ("," lambda_param)* ;
lambda_param  = IDENT (":" type_ref)? ;
```

R1では本体を単一式に限定する。

### 7.5 型推論

期待される`Fn`型がある場合、型注釈を省略できる。

```glyph
>apply(f:Fn<U,U>,x:U):U=f(x)
>run(x:U):U=apply(|n|n+1,x)
```

ここでは`apply`の第1引数から、`n:U`および戻り値`U`を推論する。

期待型がない位置では注釈を要求する。

```glyph
|n:U|n+1
```

### 7.6 capture

R1はnon-capturing lambdaだけを許可する。

許可:

```glyph
|n|n+1
|n|min(n,MAX)
```

`MAX`はcompile-time macroなのでcaptureではない。

拒否:

```glyph
>make(limit:U):Fn<U,U>=|n|min(n,limit)
```

`limit`をcaptureすると単純なRust `fn` pointerにならない。captureありclosureは所有権、lifetime、allocation契約が必要なため別機能とする。

### 7.7 純粋性

lambda本体は純粋式だけを許可する。

拒否対象:

- `!effect(...)`
- effectへ推移的に到達する関数
- 未解決callee
- monitor状態更新

### 7.8 図への表示

匿名関数は図の主要ノードにはしない。

局所式として次のように表示する。

```text
λ n -> min(n,1000) [L12]
```

長い場合:

```text
lambda@L12
```

クリックするとソース行へ移動する。

### 7.9 使用指針

ラムダ推奨:

```text
一度だけ使う
1行で理解できる
外部作用がない
主要なarchitecture nodeではない
```

名前付き関数推奨:

```text
machineのnext
systemのcomponent
主要な条件分岐
複数箇所から再利用
説明用の名前に意味がある
```

---

## 8. Lambda AST

```text
LambdaExpr
├── params: LambdaParam[]
├── body: Expr
├── expected_type: FunctionType?
├── inferred_type: FunctionType?
├── captures: SymbolId[]
└── source: SourceRef
```

R1では`captures`が空であることを検査する。

Rust生成:

```glyph
apply(|n|n+1,x)
```

```rust
apply(|n| n + 1, x)
```

non-capturing closureは期待されるfunction pointerへcoerceする。

---

## 9. Unified Design IR

```text
source
  ↓
parser AST
  ↓
AST macro expansion
  ↓
name resolution / SymbolId
  ↓
typed AST
  ├── lambda validation
  ├── purity validation
  ├── machine validation
  ├── architecture validation
  └── temporal validation
  ↓
UnifiedDesignIR
  ├── ArchitectureIR
  ├── ExecutionStructureIR
  ├── MachineIR
  └── TemporalIR
  ↓
Studio / Mermaid / Rust / source map
```

---

## 10. 出力

Studioは生成ファイル名を利用者へ意識させないが、内部では次を生成する。

```text
.glyph/<source-stem>/
├── architecture.mmd
├── machine-<name>.mmd
├── logic.mmd
├── temporal.mmd
├── overview.md
├── architecture-ir.json
├── execution-ir.json
├── typed-ast.json
├── source-map.json
├── generated.rs
└── host.generated.rs
```

---

## 11. 実装順序

### S1: `system` parser / ArchitectureIR

- `system` block抽出
- 1 edge / line parser
- componentの同名symbol自動binding
- ArchitectureIR JSON

### S2: Architecture Mermaid / Studio

- Architectureタブ
- nodeからsourceへのリンク
- sourceからdiagramへの逆引き

### S3: Logic view

- guard tree専用図
- function selector
- overviewへ4図統合

### S4: Lambda parser / Typed AST

- `LambdaExpr`
- prefix位置の`|...|`判別
- expected `Fn`型の伝播
- parameter scope
- capture解析

### S5: Lambda validation / Rust generation

- non-capturing制約
- pure expression制約
- function pointer coercion
- source map
- AST macro内lambda

### S6: Acceptance examples

- Door controller
- Job worker
- Device supervisor
- 各例を概ね500文字に収める

---

## 12. Acceptance criteria

1. `python3 glyph.py sample.glyph`だけで全ビューを開ける
2. 1接続1行の`system`宣言からArchitecture図を生成できる
3. 約500文字の例からArchitecture / State / Logic / Timeを同時表示できる
4. component nodeとソース行を相互参照できる
5. `apply(|n|n+1,x)`が型検査されRustへ生成される
6. captureありlambdaとeffectful lambdaを明示エラーにする
7. lambdaを使わない既存コードの生成結果を変えない
8. 同一ソースから決定的なIRと図を生成する

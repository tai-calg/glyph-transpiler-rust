# Glyph kinded Contract space

この文書は、Glyph 0.4 Contract spaceの表面構文と、現在の実装範囲を定義する。

## 目的

通常の型・値と設計Contractを、名前解決だけでなく字句上も区別する。

```glyph
Rpc          # 通常の型・値・関数名
'Rpc         # Contract参照
```

Contractを使わない既存Glyphソースは、従来と同じパーサ・Rust生成経路を通る。

## 定義と適用

Contractの**定義**はトップレベルで行う。

```glyph
'@WorkerTask =
  Worker * App/Window/Task

'>ProcessImage =
  -> Image >> <- ProcessResult

'!SafeFailure =
  'std.timeout(30s)
  >> 'std.return_error

'?Complete30 =
  @A(start >> @E 30s finish)

'ImageWorker = {
  'WorkerTask,
  'ProcessImage,
  'SafeFailure,
  'Complete30
}
```

Contractの**適用**は、対象宣言の後ろへ`@{'Name}`を書く。

```glyph
!process(
  image:Image
):ProcessResult
  @{'ImageWorker}
```

定義と適用は次のように区別される。

```text
'@Name = ...   World Contractを定義
'>Name = ...   Protocol Contractを定義
'!Name = ...   Handler Contractを定義
'?Name = ...   Law Contractを定義
'Name = {...}  Bundle Contractを定義

'Name           Contractを参照
@{'Name}        Contractを対象へ適用
```

`@{Name}`のようなbare identifierは受理しない。

## Protocol方向

Protocolでは通信方向を次の記号で表す。

```text
-> T    呼出し側から実行側へTを送る
<- T    実行側から呼出し側へTを返す
P >> Q  Pの後にQ
```

例:

```glyph
'>SubmitJob =
  -> Job

'>RequestReply =
  -> Request >> <- Response
```

単独の`>T`と`<T`は使用しない。既存の関数宣言`>`および比較演算子`<`との認知的衝突を避けるためである。

## 型名とContract名

同じstemをObject spaceとContract spaceで使える。

```glyph
+Failed=Temporary|Permanent

'@Failed =
  Worker * App/Task
```

このとき、

```text
Failed     通常の型
'Failed    Contract
```

となる。

## Contract kind

現在のContract parserは次のkindを区別する。

```text
World
Protocol
Handler
Law
Bundle
```

次を検査する。

- Contract名の重複
- 未定義のローカルContract参照
- 非Bundle Contract内のkind不一致
- Bundleおよび適用位置でのbare identifier
- Contract依存関係の循環
- Protocol内の旧`>T` / `<T`記法

`'std.timeout(...)`のような修飾参照は外部Contract library参照として保持する。

## Public IR

Contractを使用したソースでは、次を出力する。

```text
contracts-ir.json
```

Typed Design JSONにも`contracts`を追加する。

Contractを使用しない既存ソースでは、`contracts`キーと`contracts-ir.json`を生成しない。既存Public IRのshapeを変えないためである。

## 互換性

次の条件を満たすソースでは、既存動作を維持する。

```text
resource / own / share / linkを使わない
Contract定義を使わない
@{...}を使わない
```

現時点でContract層は既存パーサより前に抽出される。Contract行と適用部分だけを空白化し、改行数を保存してから従来のコンパイル経路へ渡す。

そのため、Contractが付いた宣言のRust生成結果は、同じ宣言からContractを除いた場合と同一になる。

## 現在の実装範囲

実装済み:

- Contract namespaceの字句分離
- Contract定義と適用の抽出
- Contract kindと参照関係の検査
- Contract metadataのCompilationModel保持
- 条件付きPublic IR出力
- 既存Rust生成経路との互換性テスト

未実装:

- `own` / `share` / `link`の型検査
- `resource T[State]`の状態・obligation検査
- Worldのexecution affinityとRegion escape検査
- Protocolのduality、能力転送、反復・並行意味論
- HandlerのEffect、retry、rollback等の意味検査
- Law Contractのmodel checkingおよびruntime monitor統合
- Bundleを対象宣言へ意味論的に結合する処理

Contract syntaxを受理することと、Contractの内容を完全に保証することを区別する。

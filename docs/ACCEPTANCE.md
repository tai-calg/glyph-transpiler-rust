# Glyph v0.1 Acceptance Campaign

このcampaignは、新しい構文を増やすためのものではない。Glyphが実システムの設計骨格を一つのsource of truthとして保持し、Rust・IR・図へ決定的に変換できることを固定する。

## 実行

```bash
python3 glyphc.py examples/acceptance/door_controller.glyph --check
python3 glyphc.py examples/acceptance/job_scheduler.glyph --check
python3 glyphc.py examples/acceptance/motor_safety.glyph --check
python3 -m unittest discover -s tests -p 'test_acceptance_*.py' -v
```

通常の全試験:

```bash
python3 -m unittest discover -s tests -v
```

## Door controller

`examples/acceptance/door_controller.glyph`

検証対象:

- `system`による外部構造
- 複数行rawマクロによる接続定義
- 認証と判断を分離した`:=`アルゴリズム
- 状態機械
- 施錠期限とこじ開け安全条件
- `!lock`と`!alarm`の作用境界

期待される設計view:

```text
sensor -> authenticate -> decide -> step
                                   ├-> lock
                                   └-> alarm
```

## Compute batch runtime

`examples/acceptance/job_scheduler.glyph`

これは人員や雇用の割当ではなく、計算機上のbatchを空きlaneへ配置する例である。

検証対象:

- `/> validate?`と`/> build_batch?`のErr経路
- `~layout_lane`というRust実装の純粋境界
- `!submit_batch`という外部作用境界
- pipeline lambdaによるbatch size制限
- `manual.rs`のuser ownership

`~`と`!`は同じexternとして扱ってはならない。

```text
layout_lane   rust / pure / manual.rs
submit_batch  effect / host adapter
```

## Motor safety

`examples/acceptance/motor_safety.glyph`

検証対象:

- `@NORMALIZE ... @end`による複数行アルゴリズム展開
- lambda pipeline
- emergency/fault時の停止判断
- Motor state machine
- 100ms以内の停止制約
- `!write_motor`だけが外部作用であること
- 展開後の`normalized`が元の`NORMALIZE`呼出し行へmapされること

## 固定する不変条件

自動試験は次を固定する。

1. 同一sourceからRust・typed design・全diagram artifactが決定的に生成される。
2. 公開JSONは`schema`と`version`を持つ。
3. `logic.mmd`と`algorithm-ir.json`へ`__glyph_*`が漏れない。
4. DoorのArchitecture、Machine、Temporal constraintsが同時に存在する。
5. Compute batch runtimeでRust境界、effect境界、Err経路が区別される。
6. `manual.rs`は再buildで上書きされない。
7. Motorの複数行macroは元の呼出し行へremapされる。
8. Motorの外部作用は`write_motor`だけである。
9. Algorithm IRのbinding順と生成Rustの`let`順が一致する。

## Machine-readable artifacts

各exampleから少なくとも次を生成する。

```text
preprocessor-map.json
architecture-ir.json
algorithm-ir.json
execution-ir.json
source-map.json
typed-ast.json
logic.mmd
machine-*.mmd
temporal.mmd
generated.rs
host.generated.rs
manual.rs scaffold
```

Golden fileの全文を固定するのではなく、schema、順序、境界、source ownershipなどの意味的不変条件を検査する。整形だけの変更で大量のsnapshot更新を発生させないためである。

## v0.1完了条件

- 3 exampleが`glyphc --check`を通る
- acceptance testsが通る
- 全CIが成功する
- 新しい文法を追加しない
- Draft解除とmergeは人間が明示的に判断する
